#!/usr/bin/env python3
"""
AA Report Database Layer
========================

SQLite-based storage for AA cluster optimization results.
Provides resume capability, historical tracking, and trend analysis.

Schema:
-------
- runs: Tracks each execution of the report generation
- cluster_results: Stores optimization results for each cluster
- cluster_singles: Stores individual single cluster data (current and optimal)

Features:
---------
- Resume capability: Check if cluster already processed in current run
- Historical data: Keep all results for trend analysis
- Queryable: SQL queries for analysis and reporting
- Atomic operations: Transaction support for data integrity
"""

import sqlite3
import json
import datetime
import logging
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
from contextlib import contextmanager

logger = logging.getLogger('aa_report_automation')


class AADatabase:
    """SQLite database wrapper for AA report data."""
    
    def __init__(self, db_path: str = None):
        """
        Initialize database connection.
        
        Args:
            db_path: Path to SQLite database file. 
                    If None, uses default location: ~/aa_report_cache.db
        """
        if db_path is None:
            db_path = str(Path.home() / 'aa_report_cache.db')
        
        self.db_path = db_path
        self.conn = None
        self._connect()
        self._create_schema()
        logger.info(f"Database initialized: {self.db_path}")
    
    def _connect(self):
        """Establish database connection."""
        # Use timeout to prevent "database is locked" errors
        self.conn = sqlite3.connect(self.db_path, timeout=30.0)
        self.conn.row_factory = sqlite3.Row  # Enable column access by name
        # Enable foreign keys
        self.conn.execute("PRAGMA foreign_keys = ON")
        # Enable WAL mode for better concurrency (optional, but helps)
        self.conn.execute("PRAGMA journal_mode=WAL")
    
    def _create_schema(self):
        """Create database schema if it doesn't exist."""
        cursor = self.conn.cursor()
        
        # Table: runs - tracks each execution
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS runs (
                run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_timestamp TEXT NOT NULL,
                jira_ticket TEXT,
                total_clusters INTEGER DEFAULT 0,
                processed_clusters INTEGER DEFAULT 0,
                failed_clusters INTEGER DEFAULT 0,
                status TEXT DEFAULT 'in_progress',
                csv_path TEXT,
                completed_at TEXT,
                notes TEXT
            )
        ''')
        
        # Table: cluster_results - stores multi-cluster results
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cluster_results (
                result_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                mc_uid TEXT NOT NULL,
                processed_at TEXT NOT NULL,
                status TEXT DEFAULT 'success',
                error_message TEXT,
                total_savings REAL,
                savings_percent REAL,
                FOREIGN KEY (run_id) REFERENCES runs(run_id),
                UNIQUE(run_id, mc_uid)
            )
        ''')
        
        # Table: cluster_singles - stores individual cluster data
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cluster_singles (
                single_id INTEGER PRIMARY KEY AUTOINCREMENT,
                result_id INTEGER NOT NULL,
                cluster_uid TEXT NOT NULL,
                cluster_type TEXT NOT NULL,  -- 'current' or 'optimal'
                infra_json TEXT NOT NULL,
                instance_price REAL NOT NULL,
                storage_price REAL NOT NULL,
                total_price REAL NOT NULL,
                total_instances INTEGER,
                FOREIGN KEY (result_id) REFERENCES cluster_results(result_id)
            )
        ''')

        # Table: cluster_metadata - stores cluster metadata
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cluster_metadata (
                mc_uid TEXT PRIMARY KEY,
                cluster_name TEXT,
                cloud_provider TEXT,
                region TEXT,
                account_id TEXT,
                redis_version TEXT,
                multi_az INTEGER,
                availability_zones TEXT,
                storage_type TEXT,
                created_at TEXT,
                last_updated TEXT
            )
        ''')

        # Indexes for faster queries
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_runs_timestamp 
            ON runs(run_timestamp DESC)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_cluster_results_mc_uid 
            ON cluster_results(mc_uid)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_cluster_results_run_id
            ON cluster_results(run_id)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_cluster_results_savings
            ON cluster_results(total_savings DESC)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_cluster_metadata_provider
            ON cluster_metadata(cloud_provider)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_cluster_metadata_region
            ON cluster_metadata(region)
        ''')

        # Composite indexes for better query performance
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_cluster_results_run_status
            ON cluster_results(run_id, status)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_cluster_singles_result_type
            ON cluster_singles(result_id, cluster_type)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_runs_status_timestamp
            ON runs(status, run_timestamp DESC)
        ''')

        self.conn.commit()
        logger.debug("Database schema created/verified")
    
    @contextmanager
    def transaction(self):
        """Context manager for database transactions."""
        try:
            yield self.conn
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Transaction failed, rolling back: {e}")
            raise
    
    def create_run(self, jira_ticket: str, total_clusters: int) -> int:
        """
        Create a new run record.
        
        Args:
            jira_ticket: Jira ticket ID
            total_clusters: Total number of clusters to process
            
        Returns:
            run_id: ID of the created run
        """
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO runs (run_timestamp, jira_ticket, total_clusters, status)
            VALUES (?, ?, ?, 'in_progress')
        ''', (datetime.datetime.now().isoformat(), jira_ticket, total_clusters))
        self.conn.commit()
        
        run_id = cursor.lastrowid
        logger.info(f"Created new run: run_id={run_id}, ticket={jira_ticket}, clusters={total_clusters}")
        return run_id
    
    def is_cluster_processed(self, run_id: int, mc_uid: str) -> bool:
        """
        Check if cluster was already processed in this run.
        
        Args:
            run_id: Run ID
            mc_uid: Multi-cluster UID
            
        Returns:
            True if cluster was processed successfully
        """
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT status FROM cluster_results 
            WHERE run_id = ? AND mc_uid = ?
        ''', (run_id, mc_uid))
        
        row = cursor.fetchone()
        if row and row['status'] == 'success':
            logger.debug(f"Cluster {mc_uid} already processed in run {run_id}")
            return True
        return False
    
    def save_cluster_result(self, run_id: int, mc_uid: str,
                           clusters: List[Tuple[Dict, Dict]]) -> None:
        """
        Save cluster optimization result.

        Args:
            run_id: Run ID
            mc_uid: Multi-cluster UID
            clusters: List of (current_cluster, optimal_cluster) tuples
                     Each cluster is a dict with: uid, infra, price
        """
        with self.transaction():
            cursor = self.conn.cursor()

            # Calculate total savings
            total_current = sum(c['price']['total'] for c, _ in clusters)
            total_optimal = sum(o['price']['total'] for _, o in clusters)
            total_savings = total_current - total_optimal
            savings_percent = (total_savings / total_current * 100) if total_current > 0 else 0

            # Insert cluster result with savings
            cursor.execute('''
                INSERT OR REPLACE INTO cluster_results
                (run_id, mc_uid, processed_at, status, total_savings, savings_percent)
                VALUES (?, ?, ?, 'success', ?, ?)
            ''', (run_id, mc_uid, datetime.datetime.now().isoformat(),
                  total_savings, savings_percent))

            result_id = cursor.lastrowid

            # Insert single cluster data
            for current, optimal in clusters:
                # Calculate total instances for current
                current_instances = sum(current['infra'].values())

                # Save current cluster
                cursor.execute('''
                    INSERT INTO cluster_singles
                    (result_id, cluster_uid, cluster_type, infra_json,
                     instance_price, storage_price, total_price, total_instances)
                    VALUES (?, ?, 'current', ?, ?, ?, ?, ?)
                ''', (
                    result_id,
                    current['uid'],
                    json.dumps(current['infra']),
                    current['price']['instance'],
                    current['price']['storage'],
                    current['price']['total'],
                    current_instances
                ))

                # Calculate total instances for optimal
                optimal_instances = sum(optimal['infra'].values())

                # Save optimal cluster
                cursor.execute('''
                    INSERT INTO cluster_singles
                    (result_id, cluster_uid, cluster_type, infra_json,
                     instance_price, storage_price, total_price, total_instances)
                    VALUES (?, ?, 'optimal', ?, ?, ?, ?, ?)
                ''', (
                    result_id,
                    optimal['uid'],
                    json.dumps(optimal['infra']),
                    optimal['price']['instance'],
                    optimal['price']['storage'],
                    optimal['price']['total'],
                    optimal_instances
                ))
            
            # Note: Run statistics will be updated in batch via update_run_statistics()
            # to avoid UPDATE on every cluster (performance optimization)

        logger.debug(f"Saved result for cluster {mc_uid} in run {run_id}")

    def save_cluster_metadata(self, mc_uid: str, cluster_name: str = None,
                             cloud_provider: str = None, region: str = None,
                             account_id: str = None, redis_version: str = None,
                             multi_az: bool = None, availability_zones: str = None,
                             storage_type: str = None) -> None:
        """
        Save or update cluster metadata.

        Args:
            mc_uid: Multi-cluster UID
            cluster_name: Human-readable cluster name
            cloud_provider: Cloud provider (AWS, GCP, Azure)
            region: Cloud region
            account_id: Account/Subscription ID
            redis_version: Redis version (e.g., "7.2")
            multi_az: Multi-AZ enabled (True/False)
            availability_zones: Comma-separated list of AZs
            storage_type: Storage type (gp2, gp3, io1, etc.)
        """
        with self.transaction():
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO cluster_metadata
                (mc_uid, cluster_name, cloud_provider, region, account_id,
                 redis_version, multi_az, availability_zones, storage_type, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (mc_uid, cluster_name, cloud_provider, region, account_id,
                  redis_version, 1 if multi_az else 0 if multi_az is not None else None,
                  availability_zones, storage_type,
                  datetime.datetime.now().isoformat()))

        logger.debug(f"Saved metadata for cluster {mc_uid}")

    def load_cluster_result(self, run_id: int, mc_uid: str) -> Optional[Dict]:
        """
        Load cluster result from database.
        
        Args:
            run_id: Run ID
            mc_uid: Multi-cluster UID
            
        Returns:
            Dict with 'uid' and 'clusters' (list of current/optimal pairs)
            or None if not found
        """
        cursor = self.conn.cursor()
        
        # Get result_id
        cursor.execute('''
            SELECT result_id FROM cluster_results
            WHERE run_id = ? AND mc_uid = ? AND status = 'success'
        ''', (run_id, mc_uid))
        
        row = cursor.fetchone()
        if not row:
            return None
        
        result_id = row['result_id']
        
        # Get all singles for this result
        cursor.execute('''
            SELECT cluster_uid, cluster_type, infra_json, 
                   instance_price, storage_price, total_price
            FROM cluster_singles
            WHERE result_id = ?
            ORDER BY single_id
        ''', (result_id,))
        
        singles = cursor.fetchall()
        
        # Group by cluster_uid (current and optimal pairs)
        clusters = []
        cluster_map = {}
        
        for single in singles:
            uid = single['cluster_uid']
            cluster_data = {
                'uid': uid,
                'infra': json.loads(single['infra_json']),
                'price': {
                    'instance': single['instance_price'],
                    'storage': single['storage_price'],
                    'total': single['total_price']
                }
            }
            
            if uid not in cluster_map:
                cluster_map[uid] = {}
            
            cluster_map[uid][single['cluster_type']] = cluster_data
        
        # Create pairs
        for uid, data in cluster_map.items():
            if 'current' in data and 'optimal' in data:
                clusters.append((data['current'], data['optimal']))
        
        return {
            'uid': mc_uid,
            'clusters': clusters
        }

    def mark_cluster_failed(self, run_id: int, mc_uid: str, error_message: str) -> None:
        """
        Mark cluster as failed.

        Args:
            run_id: Run ID
            mc_uid: Multi-cluster UID
            error_message: Error description
        """
        with self.transaction():
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO cluster_results
                (run_id, mc_uid, processed_at, status, error_message)
                VALUES (?, ?, ?, 'failed', ?)
            ''', (run_id, mc_uid, datetime.datetime.now().isoformat(), error_message))

            # Note: Run statistics will be updated in batch via update_run_statistics()

        logger.debug(f"Marked cluster {mc_uid} as failed in run {run_id}")

    def update_run_statistics(self, run_id: int) -> Dict[str, int]:
        """
        Update run statistics by counting cluster_results.
        This is more efficient than incrementing on every cluster save.

        Args:
            run_id: Run ID

        Returns:
            Dict with 'processed' and 'failed' counts
        """
        cursor = self.conn.cursor()

        # Get counts in a single query
        cursor.execute('''
            SELECT
                COUNT(CASE WHEN status = 'success' THEN 1 END) as processed,
                COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed
            FROM cluster_results
            WHERE run_id = ?
        ''', (run_id,))

        row = cursor.fetchone()
        processed = row['processed']
        failed = row['failed']

        # Update run record
        cursor.execute('''
            UPDATE runs
            SET processed_clusters = ?,
                failed_clusters = ?
            WHERE run_id = ?
        ''', (processed, failed, run_id))
        self.conn.commit()

        logger.debug(f"Updated statistics for run {run_id}: {processed} processed, {failed} failed")

        return {'processed': processed, 'failed': failed}

    def complete_run(self, run_id: int, csv_path: str = None) -> None:
        """
        Mark run as completed and update final statistics.

        Args:
            run_id: Run ID
            csv_path: Path to generated CSV file
        """
        # Update statistics before completing
        self.update_run_statistics(run_id)

        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE runs
            SET status = 'completed',
                completed_at = ?,
                csv_path = ?
            WHERE run_id = ?
        ''', (datetime.datetime.now().isoformat(), csv_path, run_id))
        self.conn.commit()

        logger.info(f"Run {run_id} marked as completed")

    def get_all_results_for_run(self, run_id: int) -> List[Dict]:
        """
        Get all cluster results for a specific run.
        Optimized to use a single JOIN query instead of N+1 queries.

        Args:
            run_id: Run ID

        Returns:
            List of cluster result dicts
        """
        cursor = self.conn.cursor()

        # Single query with JOIN - much faster than N queries
        cursor.execute('''
            SELECT
                cr.mc_uid,
                cs.cluster_uid,
                cs.cluster_type,
                cs.infra_json,
                cs.instance_price,
                cs.storage_price,
                cs.total_price
            FROM cluster_results cr
            JOIN cluster_singles cs ON cr.result_id = cs.result_id
            WHERE cr.run_id = ? AND cr.status = 'success'
            ORDER BY cr.processed_at, cs.single_id
        ''', (run_id,))

        # Group results by mc_uid
        results_map = {}
        for row in cursor.fetchall():
            mc_uid = row['mc_uid']

            if mc_uid not in results_map:
                results_map[mc_uid] = {
                    'uid': mc_uid,
                    'clusters': [],
                    'cluster_map': {}
                }

            cluster_uid = row['cluster_uid']
            cluster_data = {
                'uid': cluster_uid,
                'infra': json.loads(row['infra_json']),
                'price': {
                    'instance': row['instance_price'],
                    'storage': row['storage_price'],
                    'total': row['total_price']
                }
            }

            # Group by cluster_uid to create pairs
            if cluster_uid not in results_map[mc_uid]['cluster_map']:
                results_map[mc_uid]['cluster_map'][cluster_uid] = {}

            results_map[mc_uid]['cluster_map'][cluster_uid][row['cluster_type']] = cluster_data

        # Convert to final format
        results = []
        for mc_uid, data in results_map.items():
            clusters = []
            for cluster_uid, cluster_types in data['cluster_map'].items():
                if 'current' in cluster_types and 'optimal' in cluster_types:
                    clusters.append((cluster_types['current'], cluster_types['optimal']))

            results.append({
                'uid': mc_uid,
                'clusters': clusters
            })

        return results

    # ========================================================================
    # HISTORICAL ANALYSIS METHODS
    # ========================================================================

    def get_cluster_history(self, mc_uid: str, limit: int = 10) -> List[Dict]:
        """
        Get historical optimization data for a specific cluster.

        Args:
            mc_uid: Multi-cluster UID
            limit: Maximum number of historical records

        Returns:
            List of dicts with timestamp, current_price, optimal_price, savings
        """
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT
                r.run_timestamp AS timestamp,
                r.jira_ticket,
                cr.total_savings AS savings,
                cr.savings_percent,
                cr.result_id
            FROM cluster_results cr
            JOIN runs r ON cr.run_id = r.run_id
            WHERE cr.mc_uid = ? AND cr.status = 'success'
            ORDER BY r.run_timestamp DESC
            LIMIT ?
        ''', (mc_uid, limit))

        history = []
        for row in cursor.fetchall():
            result_id = row['result_id']

            # Get current and optimal prices (sum all singles)
            cursor.execute('''
                SELECT
                    SUM(CASE WHEN cluster_type = 'current' THEN total_price ELSE 0 END) as current_price,
                    SUM(CASE WHEN cluster_type = 'optimal' THEN total_price ELSE 0 END) as optimal_price
                FROM cluster_singles
                WHERE result_id = ?
            ''', (result_id,))

            prices_row = cursor.fetchone()
            current_price = prices_row['current_price'] or 0
            optimal_price = prices_row['optimal_price'] or 0

            history.append({
                'timestamp': row['timestamp'],
                'jira_ticket': row['jira_ticket'],
                'current_price': round(current_price, 2),
                'optimal_price': round(optimal_price, 2),
                'savings': round(row['savings'], 2),
                'savings_percent': round(row['savings_percent'], 2)
            })

        return history

    def get_total_savings_trend(self, limit: int = 10) -> List[Dict]:
        """
        Get trend of total potential savings across all clusters.

        Args:
            limit: Number of recent runs to analyze

        Returns:
            List of dicts with timestamp, total_current, total_optimal, total_savings
        """
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT
                r.run_timestamp AS timestamp,
                r.jira_ticket,
                SUM(cr.total_savings) AS total_savings,
                SUM(CASE WHEN cs.cluster_type = 'current' THEN cs.total_price ELSE 0 END) as total_current,
                SUM(CASE WHEN cs.cluster_type = 'optimal' THEN cs.total_price ELSE 0 END) as total_optimal
            FROM runs r
            JOIN cluster_results cr ON r.run_id = cr.run_id
            JOIN cluster_singles cs ON cr.result_id = cs.result_id
            WHERE r.status = 'completed' AND cr.status = 'success'
            GROUP BY r.run_id
            ORDER BY r.run_timestamp DESC
            LIMIT ?
        ''', (limit,))

        trend = []
        for row in cursor.fetchall():
            total_current = row['total_current'] or 0
            total_optimal = row['total_optimal'] or 0
            total_savings = row['total_savings'] or 0

            trend.append({
                'timestamp': row['timestamp'],
                'jira_ticket': row['jira_ticket'],
                'total_current': round(total_current, 2),
                'total_optimal': round(total_optimal, 2),
                'total_savings': round(total_savings, 2),
                'savings_percent': round((total_current - total_optimal) / total_current * 100, 2) if total_current > 0 else 0
            })

        return trend

    def get_top_savings_opportunities(self, run_id: int = None, limit: int = None) -> List[Dict]:
        """
        Get clusters with highest potential savings.

        Args:
            run_id: Specific run ID, or None for latest run
            limit: Number of top clusters to return, or None for all

        Returns:
            List of dicts with mc_uid, current_price, optimal_price, savings
        """
        cursor = self.conn.cursor()

        # Get latest run if not specified
        if run_id is None:
            cursor.execute('''
                SELECT run_id FROM runs
                WHERE status = 'completed'
                ORDER BY run_timestamp DESC
                LIMIT 1
            ''')
            row = cursor.fetchone()
            if not row:
                return []
            run_id = row['run_id']

        # Get savings for all clusters in this run (using pre-calculated savings)
        if limit is None:
            # No limit - get all
            cursor.execute('''
                SELECT
                    cr.mc_uid,
                    cr.total_savings,
                    cr.savings_percent,
                    SUM(CASE WHEN cs.cluster_type = 'current' THEN cs.total_price ELSE 0 END) as current_price,
                    SUM(CASE WHEN cs.cluster_type = 'optimal' THEN cs.total_price ELSE 0 END) as optimal_price,
                    cm.cloud_provider,
                    cm.redis_version,
                    cm.cluster_name,
                    cm.region,
                    cm.created_at
                FROM cluster_results cr
                JOIN cluster_singles cs ON cr.result_id = cs.result_id
                LEFT JOIN cluster_metadata cm ON cr.mc_uid = cm.mc_uid
                WHERE cr.run_id = ? AND cr.status = 'success'
                GROUP BY cr.mc_uid
                ORDER BY cr.total_savings DESC
            ''', (run_id,))
        else:
            # With limit
            cursor.execute('''
                SELECT
                    cr.mc_uid,
                    cr.total_savings,
                    cr.savings_percent,
                    SUM(CASE WHEN cs.cluster_type = 'current' THEN cs.total_price ELSE 0 END) as current_price,
                    SUM(CASE WHEN cs.cluster_type = 'optimal' THEN cs.total_price ELSE 0 END) as optimal_price,
                    cm.cloud_provider,
                    cm.redis_version,
                    cm.cluster_name,
                    cm.region,
                    cm.created_at
                FROM cluster_results cr
                JOIN cluster_singles cs ON cr.result_id = cs.result_id
                LEFT JOIN cluster_metadata cm ON cr.mc_uid = cm.mc_uid
                WHERE cr.run_id = ? AND cr.status = 'success'
                GROUP BY cr.mc_uid
                ORDER BY cr.total_savings DESC
                LIMIT ?
            ''', (run_id, limit))

        opportunities = []
        for row in cursor.fetchall():
            opportunities.append({
                'mc_uid': row['mc_uid'],
                'current_price': round(row['current_price'], 2),
                'optimal_price': round(row['optimal_price'], 2),
                'savings': round(row['total_savings'], 2),
                'savings_percent': round(row['savings_percent'], 2),
                'cloud_provider': row['cloud_provider'],
                'redis_version': row['redis_version'],
                'cluster_name': row['cluster_name'],
                'region': row['region'],
                'created_at': row['created_at']
            })

        return opportunities

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logger.debug("Database connection closed")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensures connection is closed."""
        self.close()
        return False  # Don't suppress exceptions

