#!/usr/bin/env python3
# mypy: ignore-errors

"""
AA Report Automation Tool - Analyze and optimize Active-Active Redis clusters.

Usage:
    python aa_report_automation.py [--limit N] [--log-level LEVEL]

Environment Variables:
    RCP_SERVER   - RCP hostname (default: rcp-server-prod.redislabs.com)
    RCP_USERNAME - RCP username (default: operations)
    RCP_PASSWORD - RCP password (REQUIRED)

See README.md for full documentation.
"""

import os
import sys
import time
import datetime
import argparse
import logging
from typing import List, Tuple, Optional, Dict, Any
from functools import wraps
from collections import Counter
from dataclasses import dataclass
import threading

script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from aa_database import AADatabase


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class Price:
    """Pricing information (storage + instance)."""
    storage: float
    instance: float

    @property
    def total(self) -> float:
        return self.storage + self.instance


@dataclass
class Cluster:
    """Single cluster configuration."""
    uid: str
    infra: Dict[str, int]
    price: Price


@dataclass
class MultiCluster:
    """Multi-cluster (Active-Active) configuration."""
    uid: str
    clusters: List[Cluster]


@dataclass
class MultiClusterResult:
    """Optimization results (current vs optimal)."""
    uid: str
    clusters: List[Tuple[Cluster, Cluster]]

# ============================================================================
# CONFIGURATION
# ============================================================================

RCP_SERVER = os.getenv('RCP_SERVER', 'rcp-server-prod.redislabs.com')
RCP_USERNAME = os.getenv('RCP_USERNAME', 'operations')
RCP_PASSWORD = os.getenv('RCP_PASSWORD')


# ============================================================================
# LOGGING
# ============================================================================

def setup_logging(log_level: str = 'INFO') -> logging.Logger:
    log_dir = os.path.join(os.path.expanduser('~'), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f'aa_report_automation_{datetime.datetime.now().strftime("%Y-%m-%d")}.log')

    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.FileHandler(log_file), logging.StreamHandler(sys.stdout)]
    )

    logger = logging.getLogger('aa_report_automation')
    logger.info(f"Log: {log_file}")
    return logger


logger = setup_logging()


# ============================================================================
# CONFIG
# ============================================================================

class Config:
    RCP_SERVER: str = RCP_SERVER
    RCP_USERNAME: str = RCP_USERNAME
    RCP_PASSWORD: str = RCP_PASSWORD
    DB_PATH: str = os.path.join(os.path.expanduser('~'), 'aa_report_cache.db')
    MAX_RETRIES: int = 3
    RETRY_DELAY: int = 5
    RETRY_BACKOFF: int = 2
    HTTP_TIMEOUT: int = 30
    API_CALLS_PER_SECOND: float = 2.0
    MAX_WORKERS: int = 5
    ENABLE_PARALLEL: bool = False
    EXCLUDE_UIDS: List[str] = []

    @classmethod
    def validate(cls) -> bool:
        if not cls.RCP_PASSWORD:
            logger.error("RCP_PASSWORD environment variable is required")
            return False
        if not all([cls.RCP_SERVER, cls.RCP_USERNAME]):
            logger.error("RCP_SERVER and RCP_USERNAME must be set")
            return False
        return True


# ============================================================================
# UTILITIES
# ============================================================================

class RateLimiter:
    def __init__(self, calls_per_second: float = 2.0):
        self.min_interval = 1.0 / calls_per_second
        self.last_call = 0.0
        self.lock = threading.Lock()

    def wait(self):
        with self.lock:
            current_time = time.time()
            elapsed = current_time - self.last_call
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self.last_call = time.time()


def retry(max_tries: int = 3, delay_seconds: int = 5,
          backoff_factor: int = 2, exceptions: Tuple = (Exception,)):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = delay_seconds
            for attempt in range(1, max_tries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_tries:
                        logger.error(f"{func.__name__} failed after {max_tries} attempts: {e}")
                        raise
                    logger.warning(f"{func.__name__} attempt {attempt}/{max_tries} failed, retrying in {delay}s...")
                    time.sleep(delay)
                    delay *= backoff_factor
        return wrapper
    return decorator


# ============================================================================
# DATA CONVERSION
# ============================================================================

def convert_multicluster_result_to_dict(result: MultiClusterResult) -> List[Tuple[Dict, Dict]]:
    clusters = []
    for current, optimal in result.clusters:
        current_dict = {
            'uid': current.uid,
            'infra': current.infra,
            'price': {'instance': current.price.instance, 'storage': current.price.storage, 'total': current.price.total}
        }
        optimal_dict = {
            'uid': optimal.uid,
            'infra': optimal.infra,
            'price': {'instance': optimal.price.instance, 'storage': optimal.price.storage, 'total': optimal.price.total}
        }
        clusters.append((current_dict, optimal_dict))
    return clusters


# ============================================================================
# RCP CLIENT
# ============================================================================

class RCPClientWrapper:
    def __init__(self, hostname: str, username: str, password: str):
        try:
            from rcp_client import RcpClient
            self.client = RcpClient(hostname=hostname, username=username, password=password)
            logger.info(f"Connected to RCP: {hostname}")
        except Exception as e:
            logger.error(f"Failed to connect to RCP: {e}")
            raise

    def get_all_multi_clusters(self) -> List[Dict[str, Any]]:
        result = self.client.get_multi_clusters().result()
        logger.info(f"Retrieved {len(result)} multi-clusters")
        return result

    def get_multi_cluster_status(self, mc_uid: str) -> str:
        return self.client.get_multi_cluster_status(mc_uid).result().marshal()['status']

    def is_active(self, mc_uid: str) -> bool:
        return self.get_multi_cluster_status(mc_uid) == 'done'

    def get_multi_cluster_blueprint(self, mc_uid: str) -> Dict[str, Any]:
        return self.client.get_multi_cluster_blueprint(multi_cluster_uid=mc_uid).result().marshal()

    def plan_optimal_multi_cluster(self, mc_uid: str) -> Dict[str, Any]:
        return self.client.plan_optimal_multi_cluster(
            multi_cluster_uid=mc_uid,
            optimal_multi_cluster_request={},
            fetch_db_specs=True,
            feedback_logger=None
        ).result().marshal()['result']


def convert_blueprint_to_dataclass(mc_uid: str, mc_bp: Dict[str, Any]) -> MultiCluster:
    singles = []
    for single in mc_bp['blueprints']:
        blueprint = single['blueprint']
        cluster_uid = single['cluster_uid']
        instance_price = blueprint['usd_per_month']['cluster']
        storage_price = blueprint['usd_per_month']['storage']
        all_instances = Counter([node['instance_type'] for node in blueprint['nodes']])
        infra = dict(all_instances)
        price = Price(storage=round(storage_price, 2), instance=round(instance_price, 2))
        singles.append(Cluster(uid=cluster_uid, infra=infra, price=price))
    return MultiCluster(uid=mc_uid, clusters=singles)


def convert_plan_to_dataclass(mc_uid: str, optimal_plan: Dict[str, Any]) -> MultiCluster:
    singles = []
    for single in optimal_plan['blueprints']:
        blueprint = single['blueprint']
        cluster_uid = single['cluster_uid']
        instance_price = blueprint['usd_per_month']['cluster']
        storage_price = blueprint['usd_per_month']['storage']
        all_instances = Counter([node['instance_type'] for node in blueprint['nodes']])
        infra = dict(all_instances)
        price = Price(storage=round(storage_price, 2), instance=round(instance_price, 2))
        singles.append(Cluster(uid=cluster_uid, infra=infra, price=price))
    return MultiCluster(uid=mc_uid, clusters=singles)


# ============================================================================
# METADATA EXTRACTION
# ============================================================================

def extract_cluster_metadata(mc_uid: str, blueprint: Dict) -> Dict:
    """
    Extract metadata from blueprint response.

    Args:
        mc_uid: Multi-cluster UID
        blueprint: Blueprint response from RCP API

    Returns:
        Dict with metadata fields for save_cluster_metadata()
    """
    metadata = {
        'mc_uid': mc_uid,
        'cluster_name': None,
        'cloud_provider': None,
        'region': None,
        'account_id': None,
        'redis_version': None,
        'multi_az': None,
        'availability_zones': None,
        'storage_type': None,
        # New fields
        'creation_date': None,
        'shards_count': None,
        'max_shards_count': None,
        'total_storage_gb': None,
        'data_nodes_count': None,
        'quorum_nodes_count': None,
        'total_nodes_count': None,
        'os_version': None,
        'software_version': None,
        'rof_enabled': None
    }

    if not blueprint or 'blueprints' not in blueprint or not blueprint['blueprints']:
        return metadata

    # Extract from first cluster blueprint
    first_bp = blueprint['blueprints'][0].get('blueprint', {})

    # Extract cloud info
    cloud = first_bp.get('cloud', {})
    provider = cloud.get('provider', '').lower()

    # Cloud provider (normalize to uppercase)
    if provider == 'aws':
        metadata['cloud_provider'] = 'AWS'
    elif provider == 'gcp':
        metadata['cloud_provider'] = 'GCP'
    elif provider == 'azure':
        metadata['cloud_provider'] = 'Azure'

    # Region (different location for each provider)
    if provider == 'aws':
        # AWS: region is directly in cloud object
        metadata['region'] = cloud.get('region', '')
    elif provider == 'gcp':
        # GCP: region is nested in cloud['gcp']
        metadata['region'] = cloud.get('gcp', {}).get('region', '')
    elif provider == 'azure':
        # Azure: region is nested in cloud['azure']
        metadata['region'] = cloud.get('azure', {}).get('region', '')

    # Extract cluster info
    cluster = first_bp.get('cluster', {})
    metadata['cluster_name'] = cluster.get('name', '')
    metadata['redis_version'] = cluster.get('redis_version', '')
    metadata['multi_az'] = cluster.get('multi_az', False)

    # NEW: Extract additional cluster info
    metadata['shards_count'] = cluster.get('shards_count')
    metadata['max_shards_count'] = cluster.get('max_shards_count')
    metadata['os_version'] = cluster.get('desired_os_version', '')
    metadata['software_version'] = cluster.get('desired_software_version', '')
    metadata['rof_enabled'] = cluster.get('rof', False)

    # NEW: Extract creation date from metadata
    bp_metadata = first_bp.get('metadata', {})
    creation_time = bp_metadata.get('creation_time', '')
    if creation_time:
        # Extract just the date part (YYYY-MM-DD)
        metadata['creation_date'] = creation_time.split('T')[0] if 'T' in creation_time else creation_time

    # Extract availability zones, storage types, and node counts from nodes
    nodes = first_bp.get('nodes', [])
    azs = set()
    storage_types = set()
    total_storage_gb = 0
    data_nodes = 0
    quorum_nodes = 0

    for node in nodes:
        # Availability zones
        if 'availability_zone' in node:
            azs.add(node['availability_zone'])

        # Node counts
        if node.get('quorum_only', False):
            quorum_nodes += 1
        else:
            data_nodes += 1

        # Storage types and sizes (different for each provider)
        if provider == 'aws':
            # AWS uses ebs_volume (singular)
            ebs = node.get('ebs_volume', {})
            if 'volume_type' in ebs:
                storage_types.add(ebs['volume_type'])
            if 'volume_size' in ebs:
                total_storage_gb += ebs['volume_size']
        elif provider == 'gcp':
            # GCP uses gcp_disks (plural, array)
            gcp_disks = node.get('gcp_disks', [])
            for disk in gcp_disks:
                if 'type' in disk:
                    storage_types.add(disk['type'])
                if 'size' in disk:
                    total_storage_gb += disk['size']
        elif provider == 'azure':
            # Azure uses azure_disks (plural, array)
            azure_disks = node.get('azure_disks', [])
            for disk in azure_disks:
                if 'type' in disk:
                    storage_types.add(disk['type'])
                if 'size' in disk:
                    total_storage_gb += disk['size']

    metadata['availability_zones'] = ','.join(sorted(azs)) if azs else ''
    metadata['storage_type'] = ','.join(sorted(storage_types)) if storage_types else ''
    metadata['total_storage_gb'] = total_storage_gb if total_storage_gb > 0 else None
    metadata['data_nodes_count'] = data_nodes
    metadata['quorum_nodes_count'] = quorum_nodes
    metadata['total_nodes_count'] = data_nodes + quorum_nodes

    return metadata


# ============================================================================
# CLUSTER PROCESSING
# ============================================================================

def handle_aa_cluster(rcp_client: RCPClientWrapper, mc_uid: str,
                     db: AADatabase, run_id: int, rate_limiter: RateLimiter) -> Optional[MultiClusterResult]:
    logger.info(f"Processing {mc_uid}")
    try:
        if db.is_cluster_processed(run_id, mc_uid):
            logger.info(f"{mc_uid} already processed, skipping")
            return None

        rate_limiter.wait()
        if not rcp_client.is_active(mc_uid):
            logger.warning(f"{mc_uid} not active, skipping")
            return None

        rate_limiter.wait()
        current_bp = rcp_client.get_multi_cluster_blueprint(mc_uid)

        # Extract and save metadata
        metadata = extract_cluster_metadata(mc_uid, current_bp)
        db.save_cluster_metadata(**metadata)
        logger.debug(f"Saved metadata for {mc_uid}: {metadata.get('cluster_name', 'N/A')}")

        current_mc = convert_blueprint_to_dataclass(mc_uid, current_bp)

        rate_limiter.wait()
        optimal_plan = rcp_client.plan_optimal_multi_cluster(mc_uid)
        optimal_mc = convert_plan_to_dataclass(mc_uid, optimal_plan)

        clusters = []
        for current_single in current_mc.clusters:
            matching_optimal = [c for c in optimal_mc.clusters if current_single.uid == c.uid][0]
            clusters.append((current_single, matching_optimal))

        result = MultiClusterResult(uid=mc_uid, clusters=clusters)
        db.save_cluster_result(run_id, result)
        logger.info(f"Processed {mc_uid}")
        return result
    except Exception as e:
        logger.error(f"Failed {mc_uid}: {e}")
        return None


def generate_aa_report(rcp_client: RCPClientWrapper, db: AADatabase,
                      run_id: int, limit: Optional[int] = None) -> int:
    logger.info("Starting report generation")
    all_mc = rcp_client.get_all_multi_clusters()
    all_mc = [mc for mc in all_mc if mc['multi_cluster_uid'] not in Config.EXCLUDE_UIDS]

    if limit is not None and limit > 0:
        all_mc = all_mc[:limit]
        logger.info(f"Limited to {limit} clusters")

    total_clusters = len(all_mc)
    logger.info(f"Processing {total_clusters} clusters")
    rate_limiter = RateLimiter(calls_per_second=Config.API_CALLS_PER_SECOND)

    processed_count = 0
    for idx, mc in enumerate(all_mc, 1):
        mc_uid = mc['multi_cluster_uid']
        logger.info(f"{idx}/{total_clusters}: {mc_uid}")
        result = handle_aa_cluster(rcp_client, mc_uid, db, run_id, rate_limiter)
        if result:
            processed_count += 1

    logger.info(f"Completed: {processed_count}/{total_clusters}")
    return processed_count


# ============================================================================
# MAIN
# ============================================================================

def run_report_generation(limit: Optional[int] = None) -> None:
    logger.info("="*80)
    logger.info("AA Report Automation - Starting")
    logger.info("="*80)

    if not Config.validate():
        logger.error("Config validation failed")
        sys.exit(1)

    db = AADatabase(Config.DB_PATH)
    logger.info(f"Database: {Config.DB_PATH}")

    try:
        rcp_client = RCPClientWrapper(Config.RCP_SERVER, Config.RCP_USERNAME, Config.RCP_PASSWORD)
        all_mc = rcp_client.get_all_multi_clusters()
        all_mc = [mc for mc in all_mc if mc['multi_cluster_uid'] not in Config.EXCLUDE_UIDS]
        if limit is not None and limit > 0:
            all_mc = all_mc[:limit]
        total_clusters = len(all_mc)

        run_id = db.create_run(f"run_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}", total_clusters)
        logger.info(f"Run ID: {run_id}")

        processed_count = generate_aa_report(rcp_client, db, run_id, limit=limit)
        db.complete_run(run_id, None)

        logger.info("="*80)
        logger.info(f"Completed: {processed_count}/{total_clusters}")
        logger.info(f"Database: {Config.DB_PATH}")
        logger.info("="*80)
    except Exception as e:
        logger.exception(f"Failed: {e}")
        sys.exit(1)
    finally:
        db.close()


# ============================================================================
# CLI
# ============================================================================

def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='AA Report Automation - Analyze and optimize Active-Active clusters',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s
  %(prog)s --limit 5
  %(prog)s --log-level DEBUG

Environment Variables:
  RCP_SERVER   - RCP hostname (default: rcp-server-prod.redislabs.com)
  RCP_USERNAME - RCP username (default: operations)
  RCP_PASSWORD - RCP password (REQUIRED)
        """
    )
    parser.add_argument('--limit', type=int, help='Limit clusters (for testing)')
    parser.add_argument('--log-level', type=str, default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                       help='Log level (default: INFO)')
    return parser.parse_args()


def main():
    args = parse_arguments()
    global logger
    logger = setup_logging(args.log_level)
    run_report_generation(limit=args.limit)


if __name__ == '__main__':
    main()

