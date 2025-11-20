#!/usr/bin/env python3
"""
AA Report Web UI
================

Flask web application for visualizing AA cluster optimization data.

Usage:
    python app.py

Then open browser at: http://localhost:5000
"""

import os
import sys
import json
import logging
import re
from functools import wraps
from flask import Flask, render_template, jsonify, request, send_file
from pathlib import Path

# Load environment variables from .env file (if python-dotenv is installed)
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
        print(f"[OK] Loaded environment variables from {env_path}")
except ImportError:
    print("[INFO] python-dotenv not installed. Using system environment variables only.")
    print("       Install with: pip install python-dotenv")

# Import database module
from aa_database import AADatabase

# Initialize Flask app
app = Flask(__name__)

# FIXED: Use environment variable for secret key
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(24).hex())

# Disable template caching in development
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

# ============================================================================
# CONSTANTS AND CONFIGURATION
# ============================================================================

# Adjustment factor for conservative financial estimates
# RCP blueprint values are multiplied by this factor for display
ADJUSTMENT_FACTOR = 0.6  # 40% reduction (shows 60% of original)

# Database Path Configuration
# For Cloud Run: uses GCS mounted volume
# For local dev: uses current directory
GCS_MOUNT_PATH = os.environ.get('GCS_MOUNT_PATH')
if GCS_MOUNT_PATH:
    # Cloud Run: database in GCS bucket
    DB_PATH = os.path.join(GCS_MOUNT_PATH, 'aa_report_cache.db')
else:
    # Local development: database in current directory
    DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'aa_report_cache.db')

# Path prefix for Load Balancer routing (e.g., /aac)
PATH_PREFIX = os.environ.get('PATH_PREFIX', '').rstrip('/')
if PATH_PREFIX:
    app.config['APPLICATION_ROOT'] = PATH_PREFIX

    # Add middleware to handle path prefix
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_prefix=1)

    # Middleware to strip path prefix from incoming requests
    class PrefixMiddleware:
        def __init__(self, app, prefix):
            self.app = app
            self.prefix = prefix

        def __call__(self, environ, start_response):
            # Strip the prefix from PATH_INFO if present
            if environ['PATH_INFO'].startswith(self.prefix):
                environ['PATH_INFO'] = environ['PATH_INFO'][len(self.prefix):]
                environ['SCRIPT_NAME'] = self.prefix
                if environ['PATH_INFO'] == '':
                    environ['PATH_INFO'] = '/'
            return self.app(environ, start_response)

    app.wsgi_app = PrefixMiddleware(app.wsgi_app, PATH_PREFIX)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Log configuration
logger.info(f"Environment: {'Cloud Run' if GCS_MOUNT_PATH else 'Local Development'}")
logger.info(f"Database Path: {DB_PATH}")
logger.info(f"Path Prefix: {PATH_PREFIX if PATH_PREFIX else '(none)'}")


# ============================================================================
# JINJA2 FILTERS
# ============================================================================

@app.template_filter('adjusted')
def adjusted_filter(value):
    """Apply adjustment factor to financial value."""
    if value is None:
        return 0
    return value * ADJUSTMENT_FACTOR

@app.template_filter('format_currency')
def format_currency_filter(value, decimals=2):
    """Format value as currency with commas."""
    if value is None:
        return "$0.00"
    format_str = "{:,.%df}" % decimals
    return "$" + format_str.format(value)


# ============================================================================
# CONTEXT PROCESSORS
# ============================================================================

@app.context_processor
def inject_path_prefix():
    """Inject PATH_PREFIX and ADJUSTMENT_FACTOR into all templates."""
    return {
        'PATH_PREFIX': PATH_PREFIX,
        'ADJUSTMENT_FACTOR': ADJUSTMENT_FACTOR
    }


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_latest_run_id():
    """Get the latest completed run ID from database."""
    try:
        with AADatabase(DB_PATH) as db:
            latest = db.conn.execute(
                'SELECT run_id FROM runs WHERE status = "completed" ORDER BY run_timestamp DESC LIMIT 1'
            ).fetchone()
            return latest['run_id'] if latest else None
    except Exception as e:
        logger.error(f"Error getting latest run ID: {e}")
        return None


def get_run_id_or_latest(run_id=None):
    """Get run_id from parameter or fetch latest completed run."""
    if run_id:
        return run_id
    return get_latest_run_id()


def validate_mc_uid(mc_uid):
    """Validate cluster UID format."""
    if not mc_uid or not isinstance(mc_uid, str):
        return False
    # Allow alphanumeric, hyphens, underscores
    return bool(re.match(r'^[a-zA-Z0-9_-]+$', mc_uid))


def validate_run_id(run_id):
    """Validate run_id is a positive integer."""
    if run_id is None:
        return True  # None is valid (will use latest)
    try:
        return isinstance(run_id, int) and run_id > 0
    except:
        return False


def handle_api_error(func):
    """Decorator to handle API errors consistently."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500
    return wrapper


# ============================================================================
# ROUTES
# ============================================================================

@app.route('/')
@handle_api_error
def dashboard():
    """Main dashboard page."""
    # Use context manager to prevent connection leak
    with AADatabase(DB_PATH) as db:
        # Get latest run
        latest_run = db.conn.execute('''
            SELECT * FROM runs
            WHERE status = 'completed'
            ORDER BY run_timestamp DESC
            LIMIT 1
        ''').fetchone()

        if not latest_run:
            return render_template('dashboard.html',
                                 latest_run=None,
                                 stats=None,
                                 metrics=None,
                                 top_savings=[],
                                 trend=[])

        run_id = latest_run['run_id']

        # Get statistics
        stats = {
            'run_id': run_id,
            'timestamp': latest_run['run_timestamp'],
            'jira_ticket': latest_run['jira_ticket'],
            'total_clusters': latest_run['total_clusters'],
            'processed': latest_run['processed_clusters'],
            'failed': latest_run['failed_clusters'],
        }

        # Calculate comprehensive metrics (ONLY for clusters with positive savings)
        # Note: We use subqueries for total_savings and avg_savings to avoid duplication from JOIN
        metrics_data = db.conn.execute('''
            SELECT
                (SELECT SUM(total_savings) FROM cluster_results
                 WHERE run_id = ? AND status = 'success' AND total_savings > 0) as total_savings,
                SUM(CASE WHEN cs.cluster_type = 'current' THEN cs.total_price ELSE 0 END) as total_current,
                SUM(CASE WHEN cs.cluster_type = 'optimal' THEN cs.total_price ELSE 0 END) as total_optimal,
                (SELECT AVG(total_savings) FROM cluster_results
                 WHERE run_id = ? AND status = 'success' AND total_savings > 0) as avg_savings,
                COUNT(DISTINCT cr.mc_uid) as optimizable_clusters,
                COUNT(DISTINCT CASE WHEN cr.total_savings > 2000 THEN cr.mc_uid END) as high_impact_clusters
            FROM cluster_results cr
            JOIN cluster_singles cs ON cr.result_id = cs.result_id
            WHERE cr.run_id = ? AND cr.status = 'success' AND cr.total_savings > 0
        ''', (run_id, run_id, run_id)).fetchone()

        total_savings = metrics_data['total_savings'] or 0
        total_current = metrics_data['total_current'] or 0
        total_optimal = metrics_data['total_optimal'] or 0
        avg_savings = metrics_data['avg_savings'] or 0
        optimizable_clusters = metrics_data['optimizable_clusters'] or 0
        high_impact_clusters = metrics_data['high_impact_clusters'] or 0

        # Calculate median savings (only for positive savings)
        median_savings_row = db.conn.execute('''
            SELECT total_savings
            FROM cluster_results
            WHERE run_id = ? AND status = 'success' AND total_savings > 0
            ORDER BY total_savings
            LIMIT 1 OFFSET (
                SELECT COUNT(*) / 2
                FROM cluster_results
                WHERE run_id = ? AND status = 'success' AND total_savings > 0
            )
        ''', (run_id, run_id)).fetchone()
        median_savings = median_savings_row['total_savings'] if median_savings_row else 0

        # Get previous run for comparison (only positive savings)
        previous_run = db.conn.execute('''
            SELECT run_id,
                   (SELECT SUM(total_savings)
                    FROM cluster_results
                    WHERE run_id = runs.run_id AND status = 'success' AND total_savings > 0) as total_savings
            FROM runs
            WHERE status = 'completed' AND run_id < ?
            ORDER BY run_timestamp DESC
            LIMIT 1
        ''', (run_id,)).fetchone()

        # Calculate savings change percentage
        savings_change_percent = 0
        if previous_run and previous_run['total_savings']:
            prev_savings = previous_run['total_savings']
            savings_change_percent = ((total_savings - prev_savings) / prev_savings) * 100

        # Calculate optimization rate
        optimization_rate = (optimizable_clusters / stats['total_clusters'] * 100) if stats['total_clusters'] > 0 else 0

        # Calculate instance vs storage savings breakdown (only positive savings)
        storage_savings_row = db.conn.execute('''
            SELECT
                SUM(CASE WHEN cs.cluster_type = 'current' THEN cs.storage_price ELSE 0 END) -
                SUM(CASE WHEN cs.cluster_type = 'optimal' THEN cs.storage_price ELSE 0 END) as storage_savings
            FROM cluster_results cr
            JOIN cluster_singles cs ON cr.result_id = cs.result_id
            WHERE cr.run_id = ? AND cr.status = 'success' AND cr.total_savings > 0
        ''', (run_id,)).fetchone()
        storage_savings = storage_savings_row['storage_savings'] or 0

        # Calculate efficiency (how much is over-provisioned)
        efficiency_percent = (total_optimal / total_current * 100) if total_current > 0 else 100
        over_provisioned_percent = 100 - efficiency_percent

        # Build metrics dictionary
        metrics = {
            # Row 1: Financial Metrics
            'monthly_savings': round(total_savings * 0.6, 2),  # 40% reduction (60% of original)
            'monthly_savings_rcp_blueprint': round(total_savings, 2),  # Original RCP blueprint value
            'savings_change_percent': round(savings_change_percent, 1),
            'annual_roi': round(total_savings * 12 * 0.6, 2),  # 40% reduction (60% of original)
            'annual_roi_rcp_blueprint': round(total_savings * 12, 2),  # Original RCP blueprint value
            'savings_percent_of_spend': round((total_savings / total_current * 100) if total_current > 0 else 0, 1),
            'avg_savings_per_cluster': round(avg_savings, 2),
            'median_savings': round(median_savings, 2),
            'optimization_rate': round(optimization_rate, 1),
            'optimizable_clusters': optimizable_clusters,
            'total_clusters': stats['total_clusters'],

            # Row 2: Operational Metrics
            'high_impact_clusters': high_impact_clusters,
            'instance_efficiency': round(efficiency_percent, 1),
            'over_provisioned_percent': round(over_provisioned_percent, 1),
            'storage_savings': round(storage_savings, 2),
            'storage_savings_percent': round((storage_savings / total_savings * 100) if total_savings > 0 else 0, 1),
        }

        # Calculate Clusters Needing Attention (>$1K savings OR >30% cost reduction)
        attention_result = db.conn.execute("""
            SELECT COUNT(DISTINCT cr.mc_uid) as attention_count
            FROM cluster_results cr
            LEFT JOIN cluster_singles cs ON cr.result_id = cs.result_id AND cs.cluster_type = 'current'
            WHERE cr.run_id = ?
            AND cr.status = 'success'
            AND (
                cr.total_savings > 1000
                OR (cs.total_price > 0 AND (cr.total_savings / cs.total_price * 100) > 30)
            )
        """, (run_id,)).fetchone()
        metrics['clusters_needing_attention'] = attention_result['attention_count'] if attention_result else 0

        # Calculate most used instance type
        instance_counts = {}
        cluster_counts = {}  # Track how many clusters use each instance type

        results = db.conn.execute('''
            SELECT cs.infra_json
            FROM cluster_results cr
            JOIN cluster_singles cs ON cr.result_id = cs.result_id
            WHERE cr.run_id = ? AND cr.status = 'success' AND cs.cluster_type = 'current'
        ''', (run_id,)).fetchall()

        for row in results:
            infra = json.loads(row['infra_json'])
            for instance_type, count in infra.items():
                instance_counts[instance_type] = instance_counts.get(instance_type, 0) + count
                cluster_counts[instance_type] = cluster_counts.get(instance_type, 0) + 1

        if instance_counts:
            most_used_instance = max(instance_counts, key=instance_counts.get)
            most_used_count = cluster_counts[most_used_instance]

            # Calculate average cost for clusters using this instance type
            avg_cost_row = db.conn.execute('''
                SELECT AVG(cs.total_price) as avg_cost
                FROM cluster_results cr
                JOIN cluster_singles cs ON cr.result_id = cs.result_id
                WHERE cr.run_id = ? AND cs.cluster_type = 'current'
                AND cs.infra_json LIKE ?
            ''', (run_id, f'%"{most_used_instance}"%')).fetchone()

            most_used_avg_cost = avg_cost_row['avg_cost'] or 0
        else:
            most_used_instance = 'N/A'
            most_used_count = 0
            most_used_avg_cost = 0

        metrics['most_used_instance'] = most_used_instance
        metrics['most_used_instance_count'] = most_used_count
        metrics['most_used_instance_avg_cost'] = round(most_used_avg_cost, 2)

        # 🆕 NEW METRICS: Total AA Spend
        metrics['total_aa_spend'] = round(total_current * 0.6, 2)  # 40% reduction (60% of original)
        metrics['total_aa_spend_rcp_blueprint'] = round(total_current, 2)  # Original RCP blueprint value

        # 🆕 NEW METRICS: Average Cluster Age
        age_data = db.conn.execute('''
            SELECT cm.creation_date
            FROM cluster_results cr
            LEFT JOIN cluster_metadata cm ON cr.mc_uid = cm.mc_uid
            WHERE cr.run_id = ? AND cr.status = 'success' AND cm.creation_date IS NOT NULL
        ''', (run_id,)).fetchall()

        if age_data:
            from datetime import datetime
            current_date = datetime.now()
            ages_in_days = []

            for row in age_data:
                try:
                    creation_date = datetime.fromisoformat(row['creation_date'].replace('Z', '+00:00'))
                    days_old = (current_date - creation_date).days
                    ages_in_days.append(days_old)
                except (ValueError, AttributeError):
                    pass

            if ages_in_days:
                avg_age_days = sum(ages_in_days) / len(ages_in_days)
                metrics['avg_cluster_age_days'] = round(avg_age_days, 0)

                # Format display
                if avg_age_days >= 365:
                    metrics['avg_cluster_age_display'] = f"{avg_age_days / 365:.1f} years"
                elif avg_age_days >= 30:
                    metrics['avg_cluster_age_display'] = f"{avg_age_days / 30:.0f} months"
                else:
                    metrics['avg_cluster_age_display'] = f"{avg_age_days:.0f} days"

                # Oldest cluster
                metrics['oldest_cluster_days'] = max(ages_in_days)
            else:
                metrics['avg_cluster_age_days'] = 0
                metrics['avg_cluster_age_display'] = 'N/A'
                metrics['oldest_cluster_days'] = 0
        else:
            metrics['avg_cluster_age_days'] = 0
            metrics['avg_cluster_age_display'] = 'N/A'
            metrics['oldest_cluster_days'] = 0

        # Note: Top Cloud Provider metrics are calculated below in the provider_stats section

        # Calculate clusters by cloud provider
        provider_stats = db.conn.execute('''
            SELECT
                cm.cloud_provider,
                COUNT(DISTINCT cr.mc_uid) as cluster_count,
                SUM(CASE WHEN cs.cluster_type = 'current' THEN cs.total_price ELSE 0 END) as total_cost
            FROM cluster_results cr
            JOIN cluster_singles cs ON cr.result_id = cs.result_id
            LEFT JOIN cluster_metadata cm ON cr.mc_uid = cm.mc_uid
            WHERE cr.run_id = ? AND cr.status = 'success'
            GROUP BY cm.cloud_provider
            ORDER BY cluster_count DESC
        ''', (run_id,)).fetchall()

        # Get top 2 providers
        top_providers = []
        total_clusters_with_provider = sum(p['cluster_count'] for p in provider_stats if p['cloud_provider'])

        for provider in provider_stats[:2]:
            if provider['cloud_provider']:
                percentage = (provider['cluster_count'] / total_clusters_with_provider * 100) if total_clusters_with_provider > 0 else 0
                top_providers.append({
                    'name': provider['cloud_provider'],
                    'count': provider['cluster_count'],
                    'cost': round(provider['total_cost'], 2),
                    'percentage': round(percentage, 0)
                })

        metrics['top_providers'] = top_providers

        # Calculate top cloud provider for Financial Metrics
        if provider_stats and provider_stats[0]['cloud_provider']:
            top_provider = provider_stats[0]
            metrics['top_cloud_provider'] = top_provider['cloud_provider']
            metrics['top_cloud_provider_cost'] = round(top_provider['total_cost'], 2)
            metrics['top_cloud_provider_count'] = top_provider['cluster_count']
            metrics['top_cloud_provider_percentage'] = round(
                (top_provider['cluster_count'] / total_clusters_with_provider * 100) if total_clusters_with_provider > 0 else 0,
                0
            )
        else:
            metrics['top_cloud_provider'] = 'N/A'
            metrics['top_cloud_provider_cost'] = 0
            metrics['top_cloud_provider_count'] = 0
            metrics['top_cloud_provider_percentage'] = 0

        stats['total_savings'] = round(total_savings, 2)

        # Get top 10 savings
        top_savings = db.get_top_savings_opportunities(run_id=run_id, limit=10)

        # Add cluster age calculation to each cluster
        from datetime import datetime
        current_date = datetime.now()
        for cluster in top_savings:
            if cluster.get('creation_date'):
                try:
                    creation_date = datetime.fromisoformat(cluster['creation_date'].replace('Z', '+00:00'))
                    days_old = (current_date - creation_date).days
                    cluster['age_days'] = days_old
                    if days_old >= 365:
                        cluster['age_display'] = f"{days_old / 365:.1f} years"
                    else:
                        cluster['age_display'] = f"{days_old} days"
                except (ValueError, AttributeError):
                    cluster['age_days'] = None
                    cluster['age_display'] = 'N/A'
            else:
                cluster['age_days'] = None
                cluster['age_display'] = 'N/A'

        # Get savings trend (last 10 runs)
        trend = db.get_total_savings_trend(limit=10)
        trend.reverse()  # Oldest to newest for chart

        # Get recent runs history (last 10 runs)
        runs_history = db.conn.execute('''
            SELECT
                run_id,
                run_timestamp,
                jira_ticket,
                total_clusters,
                processed_clusters,
                failed_clusters,
                status,
                completed_at
            FROM runs
            ORDER BY run_timestamp DESC
            LIMIT 10
        ''').fetchall()

        runs = [dict(row) for row in runs_history]

        # No need for db.close() - context manager handles it
        return render_template('dashboard.html',
                             latest_run=latest_run,
                             stats=stats,
                             metrics=metrics,
                             top_savings=top_savings,
                             trend=trend,
                             runs=runs)




@app.route('/cluster/<mc_uid>')
@handle_api_error
def cluster_details(mc_uid):
    """Cluster details page."""
    # Validate input
    if not validate_mc_uid(mc_uid):
        logger.warning(f"Invalid mc_uid format: {mc_uid}")
        return "Invalid cluster ID format", 400

    # Use context manager
    with AADatabase(DB_PATH) as db:
        # Get latest result for this cluster
        latest_result = db.conn.execute('''
            SELECT cr.*, r.run_timestamp, r.jira_ticket
            FROM cluster_results cr
            JOIN runs r ON cr.run_id = r.run_id
            WHERE cr.mc_uid = ? AND cr.status = 'success'
            ORDER BY r.run_timestamp DESC
            LIMIT 1
        ''', (mc_uid,)).fetchone()

        if not latest_result:
            return "Cluster not found", 404

        result_id = latest_result['result_id']

        # Get current and optimal configurations
        singles = db.conn.execute('''
            SELECT * FROM cluster_singles
            WHERE result_id = ?
            ORDER BY cluster_type DESC
        ''', (result_id,)).fetchall()

        current_clusters = []
        optimal_clusters = []

        # Remove import from loop
        for single in singles:
            cluster_data = {
                'uid': single['cluster_uid'],
                'infra': json.loads(single['infra_json']),
                'instance_price': single['instance_price'],
                'storage_price': single['storage_price'],
                'total_price': single['total_price'],
                'total_instances': single['total_instances']
            }

            if single['cluster_type'] == 'current':
                current_clusters.append(cluster_data)
            else:
                optimal_clusters.append(cluster_data)

        # Get history
        history = db.get_cluster_history(mc_uid, limit=10)
        history.reverse()  # Oldest to newest for chart

        # Get metadata
        metadata = db.conn.execute('''
            SELECT * FROM cluster_metadata
            WHERE mc_uid = ?
        ''', (mc_uid,)).fetchone()

        # Calculate additional metrics
        total_current_instances = sum(c['total_instances'] for c in current_clusters)
        total_optimal_instances = sum(c['total_instances'] for c in optimal_clusters)

        # Calculate storage savings
        storage_savings = sum(c['storage_price'] for c in current_clusters) - \
                         sum(c['storage_price'] for c in optimal_clusters)

        # Calculate instance savings
        instance_savings = sum(c['instance_price'] for c in current_clusters) - \
                          sum(c['instance_price'] for c in optimal_clusters)

        # Add cluster age calculation to metadata
        metadata_dict = dict(metadata) if metadata else None
        if metadata_dict and metadata_dict.get('creation_date'):
            from datetime import datetime
            try:
                creation_date = datetime.fromisoformat(metadata_dict['creation_date'].replace('Z', '+00:00'))
                current_date = datetime.now()
                days_old = (current_date - creation_date).days
                metadata_dict['age_days'] = days_old
                if days_old >= 365:
                    metadata_dict['age_display'] = f"{days_old / 365:.1f} years"
                else:
                    metadata_dict['age_display'] = f"{days_old} days"
            except (ValueError, AttributeError):
                metadata_dict['age_days'] = None
                metadata_dict['age_display'] = 'N/A'

        return render_template('cluster_details.html',
                             mc_uid=mc_uid,
                             latest_result=dict(latest_result),
                             current_clusters=current_clusters,
                             optimal_clusters=optimal_clusters,
                             history=history,
                             metadata=metadata_dict,
                             total_current_instances=total_current_instances,
                             total_optimal_instances=total_optimal_instances,
                             storage_savings=storage_savings,
                             instance_savings=instance_savings)


@app.route('/top-savings')
@handle_api_error
def top_savings():
    """Top savings opportunities page."""
    # Use context manager
    with AADatabase(DB_PATH) as db:
        # Get run_id from query param or use latest
        run_id = request.args.get('run_id', type=int)

        # Get filters from query params
        cloud_provider_filter = request.args.get('cloud_provider', default='all', type=str)
        software_version_filter = request.args.get('software_version', default='all', type=str)
        top_n_param = request.args.get('top_n', default='all', type=str)

        # Parse top_n parameter
        if top_n_param == 'all':
            top_n = 'all'
        else:
            top_n = int(top_n_param)

        # Get all runs for dropdown
        all_runs = db.conn.execute('''
            SELECT run_id, run_timestamp, jira_ticket
            FROM runs
            WHERE status = 'completed'
            ORDER BY run_timestamp DESC
        ''').fetchall()

        # Check if we have any data
        if not all_runs:
            return render_template('top_savings.html',
                                 opportunities=[],
                                 all_runs=[],
                                 selected_run=None,
                                 cloud_provider_filter=cloud_provider_filter,
                                 cloud_providers=[],
                                 software_version_filter=software_version_filter,
                                 software_versions=[],
                                 top_n='all')

        # Get all savings (no limit)
        opportunities = db.get_top_savings_opportunities(run_id=run_id, limit=None)

        # Add cluster age calculation to each cluster
        from datetime import datetime
        current_date = datetime.now()
        for cluster in opportunities:
            if cluster.get('creation_date'):
                try:
                    creation_date = datetime.fromisoformat(cluster['creation_date'].replace('Z', '+00:00'))
                    days_old = (current_date - creation_date).days
                    cluster['age_days'] = days_old
                    if days_old >= 365:
                        cluster['age_display'] = f"{days_old / 365:.1f} years"
                    else:
                        cluster['age_display'] = f"{days_old} days"
                except (ValueError, AttributeError):
                    cluster['age_days'] = None
                    cluster['age_display'] = 'N/A'
            else:
                cluster['age_days'] = None
                cluster['age_display'] = 'N/A'

        # Get ALL unique values (before filtering) for initial dropdown population
        cloud_providers = sorted(list(set(
            opp['cloud_provider'] for opp in opportunities
            if opp.get('cloud_provider')
        )))

        software_versions = sorted(list(set(
            opp['software_version'] for opp in opportunities
            if opp.get('software_version')
        )), reverse=True)

        # Apply filters to opportunities
        if cloud_provider_filter != 'all':
            opportunities = [
                opp for opp in opportunities
                if opp.get('cloud_provider') == cloud_provider_filter
            ]

        if software_version_filter != 'all':
            opportunities = [
                opp for opp in opportunities
                if opp.get('software_version') == software_version_filter
            ]

        # Apply top_n limit
        if top_n != 'all':
            opportunities = opportunities[:top_n]

        # Calculate optimizable clusters count (positive savings only)
        optimizable_count = len([opp for opp in opportunities if opp.get('savings', 0) > 0])

        # Get selected run info
        if run_id:
            selected_run = db.conn.execute('''
                SELECT * FROM runs WHERE run_id = ?
            ''', (run_id,)).fetchone()
        else:
            selected_run = all_runs[0] if all_runs else None

        return render_template('top_savings.html',
                             opportunities=opportunities,
                             optimizable_count=optimizable_count,
                             all_runs=[dict(r) for r in all_runs],
                             selected_run=dict(selected_run) if selected_run else None,
                             cloud_provider_filter=cloud_provider_filter,
                             cloud_providers=cloud_providers,
                             software_version_filter=software_version_filter,
                             software_versions=software_versions,
                             top_n=top_n)


# ============================================================================
# HELPER FUNCTIONS FOR CHARTS
# ============================================================================

def detect_cloud_provider(instance_types):
    """
    Detect cloud provider from instance type names.

    Args:
        instance_types: List of instance type names

    Returns:
        str: 'AWS', 'GCP', 'Azure', or 'Unknown'
    """
    if not instance_types:
        return 'Unknown'

    for instance_type in instance_types:
        # AWS pattern: m5.large, r6i.xlarge, c5.2xlarge
        if '.' in instance_type and any(instance_type.startswith(prefix)
                                       for prefix in ['m', 'r', 'c', 't', 'i', 'x', 'z', 'p', 'g', 'd']):
            return 'AWS'
        # GCP pattern: n1-standard-4, n2-highmem-8, c3-highcpu-4
        elif '-' in instance_type and any(instance_type.startswith(prefix)
                                         for prefix in ['n1', 'n2', 'c2', 'c3', 'e2', 'm1', 'm2']):
            return 'GCP'
        # Azure pattern: Standard_D4s_v3
        elif instance_type.startswith('Standard_'):
            return 'Azure'

    return 'Unknown'


# ============================================================================
# CHARTS PAGE & API ENDPOINTS
# ============================================================================

@app.route('/charts')
@handle_api_error
def charts():
    """Charts and analytics page."""
    with AADatabase(DB_PATH) as db:
        # Get all runs for dropdown
        all_runs = db.conn.execute('''
            SELECT run_id, run_timestamp, jira_ticket
            FROM runs
            WHERE status = 'completed'
            ORDER BY run_timestamp DESC
        ''').fetchall()

        # Get latest run
        latest_run = db.conn.execute('''
            SELECT * FROM runs
            WHERE status = 'completed'
            ORDER BY run_timestamp DESC
            LIMIT 1
        ''').fetchone()

        return render_template('charts.html',
                             all_runs=[dict(r) for r in all_runs] if all_runs else [],
                             latest_run=dict(latest_run) if latest_run else None)


# ============================================================================
# API ENDPOINTS FOR CHARTS
# ============================================================================

@app.route('/api/metadata/filters')
@handle_api_error
def api_metadata_filters():
    """API: Get available filter values for metadata fields."""
    run_id = request.args.get('run_id', type=int)

    # Validate input
    if run_id and not validate_run_id(run_id):
        return jsonify({'error': 'Invalid run_id'}), 400

    # Use context manager
    with AADatabase(DB_PATH) as db:
        # Get unique values for each metadata field
        cursor = db.conn.cursor()

        # Regions
        regions = cursor.execute('''
            SELECT DISTINCT cm.region
            FROM cluster_metadata cm
            JOIN cluster_results cr ON cm.mc_uid = cr.mc_uid
            WHERE cr.run_id = ? AND cm.region IS NOT NULL AND cm.region != ''
            ORDER BY cm.region
        ''', (run_id,)).fetchall()

        # Redis versions
        redis_versions = cursor.execute('''
            SELECT DISTINCT cm.redis_version
            FROM cluster_metadata cm
            JOIN cluster_results cr ON cm.mc_uid = cr.mc_uid
            WHERE cr.run_id = ? AND cm.redis_version IS NOT NULL AND cm.redis_version != ''
            ORDER BY cm.redis_version
        ''', (run_id,)).fetchall()

        # Storage types (can be comma-separated, so we need to split)
        storage_types_raw = cursor.execute('''
            SELECT DISTINCT cm.storage_type
            FROM cluster_metadata cm
            JOIN cluster_results cr ON cm.mc_uid = cr.mc_uid
            WHERE cr.run_id = ? AND cm.storage_type IS NOT NULL AND cm.storage_type != ''
        ''', (run_id,)).fetchall()

        # Split comma-separated storage types
        storage_types = set()
        for row in storage_types_raw:
            if row[0]:
                for st in row[0].split(','):
                    storage_types.add(st.strip())

        result = {
            'regions': [r[0] for r in regions],
            'redis_versions': [v[0] for v in redis_versions],
            'storage_types': sorted(list(storage_types))
        }

        return jsonify(result)


@app.route('/api/dynamic-filters')
@handle_api_error
def api_dynamic_filters():
    """API: Get dynamically filtered options based on current selections."""
    # Get parameters
    run_id = request.args.get('run_id', type=int)
    cloud_provider = request.args.get('cloud_provider', default='all', type=str)
    software_version = request.args.get('software_version', default='all', type=str)

    # Use helper function
    run_id = get_run_id_or_latest(run_id)

    if not run_id:
        return jsonify({
            'cloud_providers': [],
            'redis_versions': []
        })

    # Use context manager
    with AADatabase(DB_PATH) as db:
        cursor = db.conn.cursor()

        # Build WHERE clause based on current filters
        where_conditions = ['cr.run_id = ?']
        params = [run_id]

        if cloud_provider != 'all':
            where_conditions.append('cm.cloud_provider = ?')
            params.append(cloud_provider)

        if software_version != 'all':
            where_conditions.append('COALESCE(cm.software_version, cm.redis_version) = ?')
            params.append(software_version)

        where_clause = ' AND '.join(where_conditions)

        # Remove f-string SQL injection risk
        # Build query with proper parameterization
        base_query_providers = '''
            SELECT DISTINCT cm.cloud_provider
            FROM cluster_metadata cm
            JOIN cluster_results cr ON cm.mc_uid = cr.mc_uid
            WHERE {} AND cm.cloud_provider IS NOT NULL AND cm.cloud_provider != ''
            ORDER BY cm.cloud_provider
        '''.format(where_clause)

        base_query_versions = '''
            SELECT DISTINCT COALESCE(cm.software_version, cm.redis_version) as version
            FROM cluster_metadata cm
            JOIN cluster_results cr ON cm.mc_uid = cr.mc_uid
            WHERE {} AND COALESCE(cm.software_version, cm.redis_version) IS NOT NULL AND COALESCE(cm.software_version, cm.redis_version) != ''
            ORDER BY version DESC
        '''.format(where_clause)

        # Get cloud providers
        cloud_providers = cursor.execute(base_query_providers, params).fetchall()

        # Get Software versions
        software_versions = cursor.execute(base_query_versions, params).fetchall()

        result = {
            'cloud_providers': [cp[0] for cp in cloud_providers],
            'software_versions': [sv[0] for sv in software_versions]
        }

        return jsonify(result)


@app.route('/api/charts/savings-distribution')
def api_savings_distribution():
    """API: Get savings distribution data for histogram."""
    import json
    db = AADatabase(DB_PATH)

    # Get parameters
    run_id = request.args.get('run_id', type=int)
    min_savings = request.args.get('min_savings', default=0, type=float)
    min_percent = request.args.get('min_percent', default=0, type=float)
    cloud_provider = request.args.get('cloud_provider', default='All', type=str)
    software_version = request.args.get('software_version', default='All', type=str)

    if not run_id:
        latest = db.conn.execute('SELECT run_id FROM runs WHERE status = "completed" ORDER BY run_timestamp DESC LIMIT 1').fetchone()
        run_id = latest['run_id'] if latest else None

    if not run_id:
        db.close()
        return jsonify({'labels': [], 'data': []})

    # Define savings ranges
    ranges = [
        (0, 500, '$0-$500'),
        (500, 1000, '$500-$1K'),
        (1000, 2000, '$1K-$2K'),
        (2000, 5000, '$2K-$5K'),
        (5000, 10000, '$5K-$10K'),
        (10000, float('inf'), '$10K+')
    ]

    labels = []
    data = []

    for min_val, max_val, label in ranges:
        # Build query with metadata filters
        query = '''
            SELECT cr.mc_uid, cs.infra_json, cm.cloud_provider, cm.region,
                   COALESCE(cm.software_version, cm.redis_version) as software_version, cm.storage_type
            FROM cluster_results cr
            JOIN cluster_singles cs ON cr.result_id = cs.result_id AND cs.cluster_type = 'current'
            LEFT JOIN cluster_metadata cm ON cr.mc_uid = cm.mc_uid
            WHERE cr.run_id = ? AND cr.status = 'success'
            AND cr.total_savings >= ?
            AND cr.savings_percent >= ?
        '''
        params = [run_id, min_savings, min_percent]

        # Add savings range filter
        if max_val == float('inf'):
            query += ' AND cr.total_savings >= ?'
            params.append(min_val)
        else:
            query += ' AND cr.total_savings >= ? AND cr.total_savings < ?'
            params.extend([min_val, max_val])

        # Add metadata filters
        if software_version != 'All':
            query += ' AND COALESCE(cm.software_version, cm.redis_version) = ?'
            params.append(software_version)

        results = db.conn.execute(query, params).fetchall()

        # Filter by cloud provider (from metadata or instance types)
        count = 0
        if cloud_provider == 'All':
            count = len(results)
        else:
            for row in results:
                # Try metadata first
                provider = row['cloud_provider'] if row['cloud_provider'] else None

                # Fallback to instance type detection
                if not provider:
                    infra = json.loads(row['infra_json'])
                    provider = detect_cloud_provider(list(infra.keys()))

                if provider == cloud_provider:
                    count += 1

        labels.append(label)
        data.append(count)

    db.close()
    return jsonify({'labels': labels, 'data': data})


@app.route('/api/charts/savings-breakdown')
def api_savings_breakdown():
    """API: Get instance vs storage savings breakdown for pie chart."""
    db = AADatabase(DB_PATH)

    run_id = request.args.get('run_id', type=int)
    if not run_id:
        latest = db.conn.execute('SELECT run_id FROM runs WHERE status = "completed" ORDER BY run_timestamp DESC LIMIT 1').fetchone()
        run_id = latest['run_id'] if latest else None

    if not run_id:
        db.close()
        return jsonify({'labels': [], 'data': []})

    # Calculate instance and storage savings (only positive savings)
    result = db.conn.execute('''
        SELECT
            SUM(CASE WHEN cs.cluster_type = 'current' THEN cs.instance_price ELSE 0 END) -
            SUM(CASE WHEN cs.cluster_type = 'optimal' THEN cs.instance_price ELSE 0 END) as instance_savings,
            SUM(CASE WHEN cs.cluster_type = 'current' THEN cs.storage_price ELSE 0 END) -
            SUM(CASE WHEN cs.cluster_type = 'optimal' THEN cs.storage_price ELSE 0 END) as storage_savings
        FROM cluster_results cr
        JOIN cluster_singles cs ON cr.result_id = cs.result_id
        WHERE cr.run_id = ? AND cr.status = 'success' AND cr.total_savings > 0
    ''', (run_id,)).fetchone()

    instance_savings = max(0, result['instance_savings'] or 0)
    storage_savings = max(0, result['storage_savings'] or 0)

    db.close()
    return jsonify({
        'labels': ['Instance Optimization', 'Storage Optimization'],
        'data': [round(instance_savings, 2), round(storage_savings, 2)]
    })


@app.route('/api/charts/savings-trend')
def api_savings_trend():
    """API: Get savings trend over time for line chart."""
    db = AADatabase(DB_PATH)

    limit = request.args.get('limit', default=10, type=int)

    trend = db.get_total_savings_trend(limit=limit)
    trend.reverse()  # Oldest to newest

    labels = [t['timestamp'][:10] for t in trend]
    data = [round(t['total_savings'], 2) for t in trend]
    tickets = [t['jira_ticket'] for t in trend]

    db.close()
    return jsonify({
        'labels': labels,
        'data': data,
        'tickets': tickets
    })


@app.route('/api/charts/current-vs-optimal')
def api_current_vs_optimal():
    """API: Get current vs optimal comparison data."""
    db = AADatabase(DB_PATH)

    run_id = request.args.get('run_id', type=int)
    limit = request.args.get('limit', default=10, type=int)

    if not run_id:
        latest = db.conn.execute('SELECT run_id FROM runs WHERE status = "completed" ORDER BY run_timestamp DESC LIMIT 1').fetchone()
        run_id = latest['run_id'] if latest else None

    if not run_id:
        db.close()
        return jsonify({'labels': [], 'current': [], 'optimal': []})

    # Get top clusters
    results = db.conn.execute('''
        SELECT
            cr.mc_uid,
            SUM(CASE WHEN cs.cluster_type = 'current' THEN cs.total_price ELSE 0 END) as current_price,
            SUM(CASE WHEN cs.cluster_type = 'optimal' THEN cs.total_price ELSE 0 END) as optimal_price,
            cr.total_savings
        FROM cluster_results cr
        JOIN cluster_singles cs ON cr.result_id = cs.result_id
        WHERE cr.run_id = ? AND cr.status = 'success'
        GROUP BY cr.mc_uid
        ORDER BY cr.total_savings DESC
        LIMIT ?
    ''', (run_id, limit)).fetchall()

    labels = [r['mc_uid'][:8] + '...' for r in results]
    current = [round(r['current_price'], 2) for r in results]
    optimal = [round(r['optimal_price'], 2) for r in results]

    db.close()
    return jsonify({
        'labels': labels,
        'current': current,
        'optimal': optimal
    })


@app.route('/api/charts/top-clusters')
def api_top_clusters():
    """API: Get top clusters data with filters."""
    import json
    db = AADatabase(DB_PATH)

    run_id = request.args.get('run_id', type=int)
    limit = request.args.get('limit', default=10, type=int)
    min_savings = request.args.get('min_savings', default=0, type=float)
    min_percent = request.args.get('min_percent', default=0, type=float)
    cloud_provider = request.args.get('cloud_provider', default='All', type=str)
    software_version = request.args.get('software_version', default='All', type=str)

    if not run_id:
        latest = db.conn.execute('SELECT run_id FROM runs WHERE status = "completed" ORDER BY run_timestamp DESC LIMIT 1').fetchone()
        run_id = latest['run_id'] if latest else None

    if not run_id:
        db.close()
        return jsonify({'labels': [], 'data': []})

    # Build query with metadata filters
    query = '''
        SELECT
            cr.mc_uid,
            cr.total_savings,
            cr.savings_percent,
            cs.infra_json,
            cm.cloud_provider,
            cm.region,
            COALESCE(cm.software_version, cm.redis_version) as software_version,
            cm.storage_type
        FROM cluster_results cr
        JOIN cluster_singles cs ON cr.result_id = cs.result_id AND cs.cluster_type = 'current'
        LEFT JOIN cluster_metadata cm ON cr.mc_uid = cm.mc_uid
        WHERE cr.run_id = ?
        AND cr.status = 'success'
        AND cr.total_savings >= ?
        AND cr.savings_percent >= ?
    '''
    params = [run_id, min_savings, min_percent]

    # Add metadata filters
    if software_version != 'All':
        query += ' AND COALESCE(cm.software_version, cm.redis_version) = ?'
        params.append(software_version)

    query += ' ORDER BY cr.total_savings DESC'

    results = db.conn.execute(query, params).fetchall()

    # Filter by cloud provider
    filtered_results = []
    for row in results:
        if cloud_provider == 'All':
            filtered_results.append(row)
        else:
            # Try metadata first
            provider = row['cloud_provider'] if row['cloud_provider'] else None

            # Fallback to instance type detection
            if not provider:
                infra = json.loads(row['infra_json'])
                provider = detect_cloud_provider(list(infra.keys()))

            if provider == cloud_provider:
                filtered_results.append(row)

        if len(filtered_results) >= limit:
            break

    labels = [r['mc_uid'][:12] + '...' for r in filtered_results]
    data = [round(r['total_savings'], 2) for r in filtered_results]

    db.close()
    return jsonify({
        'labels': labels,
        'data': data
    })


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def build_filter_clause(cloud_provider='All', software_version='All'):
    """Build WHERE clause and params for filtering by cloud provider and Software version."""
    where_clauses = []
    params = []

    if cloud_provider != 'All':
        where_clauses.append('cm.cloud_provider = ?')
        params.append(cloud_provider)

    if software_version != 'All':
        where_clauses.append('COALESCE(cm.software_version, cm.redis_version) = ?')
        params.append(software_version)

    return where_clauses, params


# ============================================================================
# NEW CHART APIs - TIME-BASED ANALYTICS
# ============================================================================

@app.route('/api/charts/cluster-age-distribution')
def api_cluster_age_distribution():
    """API: Get cluster age distribution histogram data."""
    from datetime import datetime
    db = AADatabase(DB_PATH)

    run_id = request.args.get('run_id', type=int)
    cloud_provider = request.args.get('cloudProvider', default='All')
    software_version = request.args.get('softwareVersion', default='All')

    if not run_id:
        latest = db.conn.execute('SELECT run_id FROM runs WHERE status = "completed" ORDER BY run_timestamp DESC LIMIT 1').fetchone()
        run_id = latest['run_id'] if latest else None

    if not run_id:
        db.close()
        return jsonify({'age_ranges': [], 'cluster_counts': [], 'total_savings': []})

    # Build filter clause
    filter_clauses, filter_params = build_filter_clause(cloud_provider, software_version)
    where_clauses = ['cr.run_id = ?', 'cr.status = "success"'] + filter_clauses
    where_clause = ' AND '.join(where_clauses)
    params = [run_id] + filter_params

    # Get clusters with creation dates
    query = '''
        SELECT
            COALESCE(cm.creation_date, cm.created_at) as creation_date,
            cr.total_savings
        FROM cluster_results cr
        LEFT JOIN cluster_metadata cm ON cr.mc_uid = cm.mc_uid
        WHERE {}
        AND COALESCE(cm.creation_date, cm.created_at) IS NOT NULL
    '''.format(where_clause)
    results = db.conn.execute(query, tuple(params)).fetchall()

    # Calculate age and categorize
    age_buckets = {
        '0-6 months': {'count': 0, 'savings': 0},
        '6-12 months': {'count': 0, 'savings': 0},
        '1-2 years': {'count': 0, 'savings': 0},
        '2-3 years': {'count': 0, 'savings': 0},
        '3+ years': {'count': 0, 'savings': 0}
    }

    now = datetime.now()
    for row in results:
        try:
            creation_date = datetime.fromisoformat(row['creation_date'].replace('Z', '+00:00'))
            age_days = (now - creation_date).days

            if age_days < 180:
                bucket = '0-6 months'
            elif age_days < 365:
                bucket = '6-12 months'
            elif age_days < 730:
                bucket = '1-2 years'
            elif age_days < 1095:
                bucket = '2-3 years'
            else:
                bucket = '3+ years'

            age_buckets[bucket]['count'] += 1
            age_buckets[bucket]['savings'] += row['total_savings']
        except (ValueError, AttributeError):
            continue

    # Prepare response
    age_ranges = list(age_buckets.keys())
    cluster_counts = [age_buckets[r]['count'] for r in age_ranges]
    total_savings = [round(age_buckets[r]['savings'], 2) for r in age_ranges]

    db.close()
    return jsonify({
        'age_ranges': age_ranges,
        'cluster_counts': cluster_counts,
        'total_savings': total_savings
    })


@app.route('/api/charts/age-vs-savings-correlation')
def api_age_vs_savings_correlation():
    """API: Get age vs savings correlation scatter plot data."""
    from datetime import datetime
    db = AADatabase(DB_PATH)

    run_id = request.args.get('run_id', type=int)
    cloud_provider = request.args.get('cloudProvider', default='All')
    software_version = request.args.get('softwareVersion', default='All')

    if not run_id:
        latest = db.conn.execute('SELECT run_id FROM runs WHERE status = "completed" ORDER BY run_timestamp DESC LIMIT 1').fetchone()
        run_id = latest['run_id'] if latest else None

    if not run_id:
        db.close()
        return jsonify({'data': []})

    # Build filter clause
    filter_clauses, filter_params = build_filter_clause(cloud_provider, software_version)
    where_clauses = ['cr.run_id = ?', 'cr.status = "success"'] + filter_clauses
    where_clause = ' AND '.join(where_clauses)
    params = [run_id] + filter_params

    # Get clusters with creation dates and savings
    query = '''
        SELECT
            cm.cluster_name,
            COALESCE(cm.creation_date, cm.created_at) as creation_date,
            cr.total_savings,
            cr.savings_percent,
            cm.cloud_provider,
            COALESCE(cm.software_version, cm.redis_version) as software_version
        FROM cluster_results cr
        LEFT JOIN cluster_metadata cm ON cr.mc_uid = cm.mc_uid
        WHERE {}
        AND COALESCE(cm.creation_date, cm.created_at) IS NOT NULL
    '''.format(where_clause)
    results = db.conn.execute(query, tuple(params)).fetchall()

    # Calculate age for each cluster
    scatter_data = []
    now = datetime.now()

    for row in results:
        try:
            creation_date = datetime.fromisoformat(row['creation_date'].replace('Z', '+00:00'))
            age_days = (now - creation_date).days

            scatter_data.append({
                'x': age_days,  # Age in days
                'y': round(row['total_savings'], 2),  # Total savings
                'label': row['cluster_name'] or 'Unknown',
                'savings_percent': round(row['savings_percent'], 1),
                'cloud_provider': row['cloud_provider'],
                'software_version': row['software_version']
            })
        except (ValueError, AttributeError):
            continue

    db.close()
    return jsonify({'data': scatter_data})


@app.route('/api/charts/multi-run-comparison')
def api_multi_run_comparison():
    """API: Get multi-run comparison data for line chart."""
    db = AADatabase(DB_PATH)

    limit = request.args.get('limit', default=10, type=int)

    # Get last N runs
    runs = db.conn.execute('''
        SELECT
            run_id,
            run_timestamp,
            jira_ticket,
            total_clusters,
            processed_clusters
        FROM runs
        WHERE status = 'completed'
        ORDER BY run_timestamp DESC
        LIMIT ?
    ''', (limit,)).fetchall()

    if not runs:
        db.close()
        return jsonify({'labels': [], 'current_cost': [], 'optimal_cost': [], 'savings': [], 'avg_savings': []})

    # Reverse to show oldest first
    runs = list(reversed(runs))

    labels = []
    current_cost_data = []
    optimal_cost_data = []
    savings_data = []
    avg_savings_data = []

    for run in runs:
        # Get aggregated data for this run (only positive savings)
        # Note: Use subquery for total_savings to avoid duplication from JOINs
        stats = db.conn.execute('''
            SELECT
                SUM(cs_current.total_price) as total_current,
                SUM(cs_optimal.total_price) as total_optimal,
                (SELECT SUM(total_savings) FROM cluster_results
                 WHERE run_id = ? AND status = 'success' AND total_savings > 0) as total_savings,
                COUNT(DISTINCT cr.result_id) as cluster_count
            FROM cluster_results cr
            LEFT JOIN cluster_singles cs_current ON cr.result_id = cs_current.result_id AND cs_current.cluster_type = 'current'
            LEFT JOIN cluster_singles cs_optimal ON cr.result_id = cs_optimal.result_id AND cs_optimal.cluster_type = 'optimal'
            WHERE cr.run_id = ? AND cr.status = 'success' AND cr.total_savings > 0
        ''', (run['run_id'], run['run_id'])).fetchone()

        if stats and stats['total_current']:
            labels.append(f"Run #{run['run_id']}\n{run['run_timestamp'][:10]}")
            current_cost_data.append(round(stats['total_current'], 2))
            optimal_cost_data.append(round(stats['total_optimal'], 2))
            savings_data.append(round(stats['total_savings'], 2))
            avg_savings_data.append(round(stats['total_savings'] / stats['cluster_count'], 2) if stats['cluster_count'] > 0 else 0)

    db.close()
    return jsonify({
        'labels': labels,
        'current_cost': current_cost_data,
        'optimal_cost': optimal_cost_data,
        'savings': savings_data,
        'avg_savings': avg_savings_data
    })


@app.route('/api/charts/savings-velocity')
def api_savings_velocity():
    """API: Get savings velocity (change between runs) for area chart."""
    db = AADatabase(DB_PATH)

    limit = request.args.get('limit', default=10, type=int)

    # Get last N runs
    runs = db.conn.execute('''
        SELECT
            run_id,
            run_timestamp
        FROM runs
        WHERE status = 'completed'
        ORDER BY run_timestamp DESC
        LIMIT ?
    ''', (limit,)).fetchall()

    if len(runs) < 2:
        db.close()
        return jsonify({'labels': [], 'velocity': [], 'colors': []})

    # Reverse to show oldest first
    runs = list(reversed(runs))

    labels = []
    velocity_data = []
    colors = []

    previous_savings = None

    for run in runs:
        # Get total savings for this run (only positive savings)
        stats = db.conn.execute('''
            SELECT SUM(cr.total_savings) as total_savings
            FROM cluster_results cr
            WHERE cr.run_id = ? AND cr.status = 'success' AND cr.total_savings > 0
        ''', (run['run_id'],)).fetchone()

        current_savings = stats['total_savings'] if stats and stats['total_savings'] else 0

        if previous_savings is not None:
            delta = current_savings - previous_savings
            labels.append(f"Run #{run['run_id']}\n{run['run_timestamp'][:10]}")
            velocity_data.append(round(delta, 2))
            colors.append('rgba(75, 192, 192, 0.6)' if delta >= 0 else 'rgba(255, 99, 132, 0.6)')

        previous_savings = current_savings

    db.close()
    return jsonify({
        'labels': labels,
        'velocity': velocity_data,
        'colors': colors
    })


# ============================================================================
# NEW CHART APIs - GEOGRAPHIC & CLOUD PROVIDER
# ============================================================================

@app.route('/api/charts/cloud-provider-comparison')
def api_cloud_provider_comparison():
    """API: Get cloud provider comparison data for stacked bar chart."""
    db = AADatabase(DB_PATH)

    run_id = request.args.get('run_id', type=int)
    cloud_provider = request.args.get('cloudProvider', default='All')
    software_version = request.args.get('softwareVersion', default='All')

    if not run_id:
        latest = db.conn.execute('SELECT run_id FROM runs WHERE status = "completed" ORDER BY run_timestamp DESC LIMIT 1').fetchone()
        run_id = latest['run_id'] if latest else None

    if not run_id:
        db.close()
        return jsonify({'providers': [], 'current_instance': [], 'current_storage': [], 'optimal_instance': [], 'optimal_storage': []})

    # Build filter clause
    filter_clauses, filter_params = build_filter_clause(cloud_provider, software_version)
    where_clauses = ['cr.run_id = ?', 'cr.status = "success"'] + filter_clauses
    where_clause = ' AND '.join(where_clauses)
    params = [run_id] + filter_params

    # Get data grouped by cloud provider
    # Use .format() instead of f-string for SQL (where_clause is from controlled code)
    query = '''
        SELECT
            cm.cloud_provider,
            SUM(cs_current.instance_price) as current_instance,
            SUM(cs_current.storage_price) as current_storage,
            SUM(cs_optimal.instance_price) as optimal_instance,
            SUM(cs_optimal.storage_price) as optimal_storage
        FROM cluster_results cr
        LEFT JOIN cluster_singles cs_current ON cr.result_id = cs_current.result_id AND cs_current.cluster_type = 'current'
        LEFT JOIN cluster_singles cs_optimal ON cr.result_id = cs_optimal.result_id AND cs_optimal.cluster_type = 'optimal'
        LEFT JOIN cluster_metadata cm ON cr.mc_uid = cm.mc_uid
        WHERE {}
        GROUP BY cm.cloud_provider
        HAVING cm.cloud_provider IS NOT NULL
        ORDER BY (current_instance + current_storage) DESC
    '''.format(where_clause)
    results = db.conn.execute(query, tuple(params)).fetchall()

    providers = []
    current_instance = []
    current_storage = []
    optimal_instance = []
    optimal_storage = []

    for row in results:
        providers.append(row['cloud_provider'])
        current_instance.append(round(row['current_instance'], 2))
        current_storage.append(round(row['current_storage'], 2))
        optimal_instance.append(round(row['optimal_instance'], 2))
        optimal_storage.append(round(row['optimal_storage'], 2))

    db.close()
    return jsonify({
        'providers': providers,
        'current_instance': current_instance,
        'current_storage': current_storage,
        'optimal_instance': optimal_instance,
        'optimal_storage': optimal_storage
    })


# ============================================================================
# NEW CHART APIs - INSTANCE TYPE & CONFIGURATION
# ============================================================================

@app.route('/api/charts/instance-efficiency-matrix')
def api_instance_efficiency_matrix():
    """API: Get instance type efficiency matrix data for scatter plot."""
    import json
    db = AADatabase(DB_PATH)

    run_id = request.args.get('run_id', type=int)
    cloud_provider = request.args.get('cloudProvider', default='All')
    software_version = request.args.get('softwareVersion', default='All')

    if not run_id:
        latest = db.conn.execute('SELECT run_id FROM runs WHERE status = "completed" ORDER BY run_timestamp DESC LIMIT 1').fetchone()
        run_id = latest['run_id'] if latest else None

    if not run_id:
        db.close()
        return jsonify({'data': []})

    # Build filter clause
    filter_clauses, filter_params = build_filter_clause(cloud_provider, software_version)
    where_clauses = ['cr.run_id = ?', 'cr.status = "success"'] + filter_clauses
    where_clause = ' AND '.join(where_clauses)
    params = [run_id] + filter_params

    # Get all clusters with their instance types
    # Use .format() instead of f-string
    query = '''
        SELECT
            cr.mc_uid,
            cs.infra_json,
            cs.total_price as current_price,
            cr.savings_percent,
            cm.cloud_provider
        FROM cluster_results cr
        JOIN cluster_singles cs ON cr.result_id = cs.result_id AND cs.cluster_type = 'current'
        LEFT JOIN cluster_metadata cm ON cr.mc_uid = cm.mc_uid
        WHERE {}
    '''.format(where_clause)
    results = db.conn.execute(query, tuple(params)).fetchall()

    # Aggregate by instance type
    instance_stats = {}

    for row in results:
        infra = json.loads(row['infra_json'])
        # Get primary instance type (most common)
        if infra:
            primary_instance = max(infra.items(), key=lambda x: x[1])[0]

            if primary_instance not in instance_stats:
                instance_stats[primary_instance] = {
                    'total_cost': 0,
                    'total_savings_percent': 0,
                    'count': 0,
                    'provider': row['cloud_provider'] or 'Unknown'
                }

            instance_stats[primary_instance]['total_cost'] += row['current_price']
            instance_stats[primary_instance]['total_savings_percent'] += row['savings_percent']
            instance_stats[primary_instance]['count'] += 1

    # Create scatter plot data
    scatter_data = []
    for instance_type, stats in instance_stats.items():
        avg_cost = stats['total_cost'] / stats['count']
        avg_savings_percent = stats['total_savings_percent'] / stats['count']

        scatter_data.append({
            'x': round(avg_cost, 2),
            'y': round(avg_savings_percent, 2),
            'r': stats['count'] * 2,  # Bubble size
            'label': instance_type,
            'count': stats['count'],
            'provider': stats['provider']
        })

    db.close()
    return jsonify({'data': scatter_data})


# ============================================================================
# NEW CHART APIs - STORAGE ANALYTICS
# ============================================================================

@app.route('/api/charts/storage-type-distribution')
def api_storage_type_distribution():
    """API: Get storage type distribution and savings."""
    db = AADatabase(DB_PATH)

    run_id = request.args.get('run_id', type=int)
    cloud_provider = request.args.get('cloudProvider', default='All')
    software_version = request.args.get('softwareVersion', default='All')

    if not run_id:
        latest = db.conn.execute('SELECT run_id FROM runs WHERE status = "completed" ORDER BY run_timestamp DESC LIMIT 1').fetchone()
        run_id = latest['run_id'] if latest else None

    if not run_id:
        db.close()
        return jsonify({'storage_types': [], 'cluster_counts': [], 'avg_savings': []})

    # Build filter clause
    filter_clauses, filter_params = build_filter_clause(cloud_provider, software_version)
    where_clauses = ['cr.run_id = ?', 'cr.status = "success"'] + filter_clauses
    where_clause = ' AND '.join(where_clauses)
    params = [run_id] + filter_params

    # Get data grouped by storage type
    # Use .format() instead of f-string
    query = '''
        SELECT
            cm.storage_type,
            COUNT(*) as cluster_count,
            AVG(cr.total_savings) as avg_savings
        FROM cluster_results cr
        LEFT JOIN cluster_metadata cm ON cr.mc_uid = cm.mc_uid
        WHERE {}
        GROUP BY cm.storage_type
        HAVING cm.storage_type IS NOT NULL
        ORDER BY cluster_count DESC
    '''.format(where_clause)
    results = db.conn.execute(query, tuple(params)).fetchall()

    storage_types = []
    cluster_counts = []
    avg_savings = []

    for row in results:
        storage_types.append(row['storage_type'] or 'Unknown')
        cluster_counts.append(row['cluster_count'])
        avg_savings.append(round(row['avg_savings'], 2))

    db.close()
    return jsonify({
        'storage_types': storage_types,
        'cluster_counts': cluster_counts,
        'avg_savings': avg_savings
    })


@app.route('/api/charts/instance-storage-breakdown')
def api_instance_storage_breakdown():
    """API: Get instance vs storage savings breakdown per cluster."""
    db = AADatabase(DB_PATH)

    run_id = request.args.get('run_id', type=int)
    limit = request.args.get('limit', default=20, type=int)

    if not run_id:
        latest = db.conn.execute('SELECT run_id FROM runs WHERE status = "completed" ORDER BY run_timestamp DESC LIMIT 1').fetchone()
        run_id = latest['run_id'] if latest else None

    if not run_id:
        db.close()
        return jsonify({'labels': [], 'instance_savings': [], 'storage_savings': []})

    # Get top clusters by total savings
    results = db.conn.execute('''
        SELECT
            cr.mc_uid,
            (cs_current.instance_price - cs_optimal.instance_price) as instance_savings,
            (cs_current.storage_price - cs_optimal.storage_price) as storage_savings,
            cr.total_savings
        FROM cluster_results cr
        LEFT JOIN cluster_singles cs_current ON cr.result_id = cs_current.result_id AND cs_current.cluster_type = 'current'
        LEFT JOIN cluster_singles cs_optimal ON cr.result_id = cs_optimal.result_id AND cs_optimal.cluster_type = 'optimal'
        WHERE cr.run_id = ? AND cr.status = 'success'
        ORDER BY cr.total_savings DESC
        LIMIT ?
    ''', (run_id, limit)).fetchall()

    labels = []
    instance_savings = []
    storage_savings = []

    for row in results:
        labels.append(row['mc_uid'][:12] + '...')
        instance_savings.append(round(row['instance_savings'], 2))
        storage_savings.append(round(row['storage_savings'], 2))

    db.close()
    return jsonify({
        'labels': labels,
        'instance_savings': instance_savings,
        'storage_savings': storage_savings
    })


# ============================================================================
# NEW CHART APIs - REDIS VERSION ANALYTICS
# ============================================================================

@app.route('/api/charts/software-version-analysis')
def api_software_version_analysis():
    """API: Get Software version adoption and cost analysis."""
    db = AADatabase(DB_PATH)

    run_id = request.args.get('run_id', type=int)

    if not run_id:
        latest = db.conn.execute('SELECT run_id FROM runs WHERE status = "completed" ORDER BY run_timestamp DESC LIMIT 1').fetchone()
        run_id = latest['run_id'] if latest else None

    if not run_id:
        db.close()
        return jsonify({'versions': [], 'cluster_counts': [], 'avg_cost': [], 'avg_savings_percent': []})

    # Get data grouped by Software version
    results = db.conn.execute('''
        SELECT
            COALESCE(cm.software_version, cm.redis_version) as version,
            COUNT(DISTINCT cr.result_id) as cluster_count,
            AVG(cs.total_price) as avg_cost,
            AVG(cr.savings_percent) as avg_savings_percent
        FROM cluster_results cr
        LEFT JOIN cluster_singles cs ON cr.result_id = cs.result_id AND cs.cluster_type = 'current'
        LEFT JOIN cluster_metadata cm ON cr.mc_uid = cm.mc_uid
        WHERE cr.run_id = ? AND cr.status = 'success'
        GROUP BY version
        HAVING version IS NOT NULL
        ORDER BY version DESC
    ''', (run_id,)).fetchall()

    versions = []
    cluster_counts = []
    avg_cost = []
    avg_savings_percent = []

    for row in results:
        versions.append(row['version'])
        cluster_counts.append(row['cluster_count'])
        avg_cost.append(round(row['avg_cost'], 2))
        avg_savings_percent.append(round(row['avg_savings_percent'], 2))

    db.close()
    return jsonify({
        'versions': versions,
        'cluster_counts': cluster_counts,
        'avg_cost': avg_cost,
        'avg_savings_percent': avg_savings_percent
    })


@app.route('/api/charts/software-version-age-analysis')
def api_software_version_age_analysis():
    """API: Get software version age analysis bubble chart data."""
    from datetime import datetime
    db = AADatabase(DB_PATH)

    run_id = request.args.get('run_id', type=int)
    cloud_provider = request.args.get('cloudProvider', default='All')
    software_version = request.args.get('softwareVersion', default='All')

    if not run_id:
        latest = db.conn.execute('SELECT run_id FROM runs WHERE status = "completed" ORDER BY run_timestamp DESC LIMIT 1').fetchone()
        run_id = latest['run_id'] if latest else None

    if not run_id:
        db.close()
        return jsonify({'data': []})

    # Build filter clause
    filter_clauses, filter_params = build_filter_clause(cloud_provider, software_version)
    where_clauses = ['cr.run_id = ?', 'cr.status = "success"'] + filter_clauses
    where_clause = ' AND '.join(where_clauses)
    params = [run_id] + filter_params

    # Get clusters with version, age, and savings
    query = '''
        SELECT
            cm.cluster_name,
            COALESCE(cm.software_version, cm.redis_version) as software_version,
            COALESCE(cm.creation_date, cm.created_at) as creation_date,
            cr.total_savings,
            cr.savings_percent,
            cm.cloud_provider,
            cm.region
        FROM cluster_results cr
        LEFT JOIN cluster_metadata cm ON cr.mc_uid = cm.mc_uid
        WHERE {}
        AND COALESCE(cm.software_version, cm.redis_version) IS NOT NULL
        AND COALESCE(cm.creation_date, cm.created_at) IS NOT NULL
    '''.format(where_clause)
    results = db.conn.execute(query, tuple(params)).fetchall()

    # Calculate age and prepare bubble data
    bubble_data = []
    now = datetime.now()

    for row in results:
        try:
            creation_date = datetime.fromisoformat(row['creation_date'].replace('Z', '+00:00'))
            age_days = (now - creation_date).days

            bubble_data.append({
                'x': row['software_version'],  # Software version
                'y': age_days,  # Age in days
                'r': round(row['total_savings'] / 100, 1),  # Bubble size (scaled down)
                'label': row['cluster_name'] or 'Unknown',
                'savings': round(row['total_savings'], 2),
                'savings_percent': round(row['savings_percent'], 1),
                'cloud_provider': row['cloud_provider'],
                'region': row['region']
            })
        except (ValueError, AttributeError):
            continue

    db.close()
    return jsonify({'data': bubble_data})


# ============================================================================
# NEW CHART APIs - CLUSTER SIZE & COMPLEXITY
# ============================================================================

@app.route('/api/charts/cluster-size-correlation')
def api_cluster_size_correlation():
    """API: Get cluster size vs savings correlation data."""
    db = AADatabase(DB_PATH)

    run_id = request.args.get('run_id', type=int)

    if not run_id:
        latest = db.conn.execute('SELECT run_id FROM runs WHERE status = "completed" ORDER BY run_timestamp DESC LIMIT 1').fetchone()
        run_id = latest['run_id'] if latest else None

    if not run_id:
        db.close()
        return jsonify({'data': []})

    # Get all clusters
    results = db.conn.execute('''
        SELECT
            cr.mc_uid,
            cs.total_price as current_price,
            cr.total_savings,
            cm.cloud_provider
        FROM cluster_results cr
        LEFT JOIN cluster_singles cs ON cr.result_id = cs.result_id AND cs.cluster_type = 'current'
        LEFT JOIN cluster_metadata cm ON cr.mc_uid = cm.mc_uid
        WHERE cr.run_id = ? AND cr.status = 'success'
    ''', (run_id,)).fetchall()

    scatter_data = []
    for row in results:
        scatter_data.append({
            'x': round(row['current_price'], 2),
            'y': round(row['total_savings'], 2),
            'label': row['mc_uid'][:12] + '...',
            'provider': row['cloud_provider'] or 'Unknown'
        })

    db.close()
    return jsonify({'data': scatter_data})


@app.route('/api/charts/shards-count-distribution')
def api_shards_count_distribution():
    """API: Get shards count distribution histogram data."""
    db = AADatabase(DB_PATH)

    run_id = request.args.get('run_id', type=int)
    cloud_provider = request.args.get('cloudProvider', default='All')
    software_version = request.args.get('softwareVersion', default='All')

    if not run_id:
        latest = db.conn.execute('SELECT run_id FROM runs WHERE status = "completed" ORDER BY run_timestamp DESC LIMIT 1').fetchone()
        run_id = latest['run_id'] if latest else None

    if not run_id:
        db.close()
        return jsonify({'shard_ranges': [], 'cluster_counts': [], 'avg_savings': [], 'utilization': []})

    # Build filter clause
    filter_clauses, filter_params = build_filter_clause(cloud_provider, software_version)
    where_clauses = ['cr.run_id = ?', 'cr.status = "success"'] + filter_clauses
    where_clause = ' AND '.join(where_clauses)
    params = [run_id] + filter_params

    # Get clusters with shards count
    query = '''
        SELECT
            cm.shards_count,
            cm.max_shards_count,
            cr.total_savings,
            cm.cluster_name
        FROM cluster_results cr
        LEFT JOIN cluster_metadata cm ON cr.mc_uid = cm.mc_uid
        WHERE {}
        AND cm.shards_count IS NOT NULL
    '''.format(where_clause)
    results = db.conn.execute(query, tuple(params)).fetchall()

    # Categorize by shard count ranges
    shard_buckets = {
        '1-10 shards': {'count': 0, 'savings': [], 'utilization': []},
        '11-50 shards': {'count': 0, 'savings': [], 'utilization': []},
        '51-100 shards': {'count': 0, 'savings': [], 'utilization': []},
        '101-200 shards': {'count': 0, 'savings': [], 'utilization': []},
        '200+ shards': {'count': 0, 'savings': [], 'utilization': []}
    }

    for row in results:
        shards = row['shards_count']
        max_shards = row['max_shards_count']

        if shards <= 10:
            bucket = '1-10 shards'
        elif shards <= 50:
            bucket = '11-50 shards'
        elif shards <= 100:
            bucket = '51-100 shards'
        elif shards <= 200:
            bucket = '101-200 shards'
        else:
            bucket = '200+ shards'

        shard_buckets[bucket]['count'] += 1
        shard_buckets[bucket]['savings'].append(row['total_savings'])

        # Calculate utilization percentage
        if max_shards and max_shards > 0:
            utilization = (shards / max_shards) * 100
            shard_buckets[bucket]['utilization'].append(utilization)

    # Prepare response
    shard_ranges = list(shard_buckets.keys())
    cluster_counts = [shard_buckets[r]['count'] for r in shard_ranges]
    avg_savings = [
        round(sum(shard_buckets[r]['savings']) / len(shard_buckets[r]['savings']), 2)
        if shard_buckets[r]['savings'] else 0
        for r in shard_ranges
    ]
    avg_utilization = [
        round(sum(shard_buckets[r]['utilization']) / len(shard_buckets[r]['utilization']), 1)
        if shard_buckets[r]['utilization'] else 0
        for r in shard_ranges
    ]

    db.close()
    return jsonify({
        'shard_ranges': shard_ranges,
        'cluster_counts': cluster_counts,
        'avg_savings': avg_savings,
        'utilization': avg_utilization
    })


# ============================================================================
# NEW CHART APIs - COMPARISON & BENCHMARKING
# ============================================================================

@app.route('/api/charts/current-vs-optimal-radar')
def api_current_vs_optimal_radar():
    """API: Get current vs optimal radar chart data."""
    import json
    db = AADatabase(DB_PATH)

    run_id = request.args.get('run_id', type=int)
    cloud_provider = request.args.get('cloudProvider', default='All')
    software_version = request.args.get('softwareVersion', default='All')

    if not run_id:
        latest = db.conn.execute('SELECT run_id FROM runs WHERE status = "completed" ORDER BY run_timestamp DESC LIMIT 1').fetchone()
        run_id = latest['run_id'] if latest else None

    if not run_id:
        db.close()
        return jsonify({'labels': [], 'current': [], 'optimal': []})

    # Build filter clause
    filter_clauses, filter_params = build_filter_clause(cloud_provider, software_version)
    where_clauses = ['cr.run_id = ?', 'cr.status = "success"'] + filter_clauses
    where_clause = ' AND '.join(where_clauses)
    params = [run_id] + filter_params

    # Calculate aggregate metrics
    # Use .format() instead of f-string
    query = '''
        SELECT
            SUM(cs_current.total_price) as total_current_cost,
            SUM(cs_optimal.total_price) as total_optimal_cost,
            AVG(cs_current.total_price) as avg_current_cost,
            AVG(cs_optimal.total_price) as avg_optimal_cost,
            COUNT(DISTINCT cr.result_id) as cluster_count
        FROM cluster_results cr
        LEFT JOIN cluster_singles cs_current ON cr.result_id = cs_current.result_id AND cs_current.cluster_type = 'current'
        LEFT JOIN cluster_singles cs_optimal ON cr.result_id = cs_optimal.result_id AND cs_optimal.cluster_type = 'optimal'
        LEFT JOIN cluster_metadata cm ON cr.mc_uid = cm.mc_uid
        WHERE {}
    '''.format(where_clause)
    stats = db.conn.execute(query, tuple(params)).fetchone()

    # Get instance counts
    current_instances = db.conn.execute('''
        SELECT cs.infra_json
        FROM cluster_results cr
        JOIN cluster_singles cs ON cr.result_id = cs.result_id AND cs.cluster_type = 'current'
        WHERE cr.run_id = ?
    ''', (run_id,)).fetchall()

    optimal_instances = db.conn.execute('''
        SELECT cs.infra_json
        FROM cluster_results cr
        JOIN cluster_singles cs ON cr.result_id = cs.result_id AND cs.cluster_type = 'optimal'
        WHERE cr.run_id = ?
    ''', (run_id,)).fetchall()

    # Count total instances
    current_instance_count = 0
    for row in current_instances:
        infra = json.loads(row['infra_json'])
        current_instance_count += sum(infra.values())

    optimal_instance_count = 0
    for row in optimal_instances:
        infra = json.loads(row['infra_json'])
        optimal_instance_count += sum(infra.values())

    # Normalize values for radar chart (0-100 scale)
    max_cost = max(stats['total_current_cost'], stats['total_optimal_cost'])
    max_instances = max(current_instance_count, optimal_instance_count)

    labels = ['Total Cost', 'Avg Cost per Cluster', 'Total Instances', 'Cluster Count', 'Efficiency']

    current_data = [
        round((stats['total_current_cost'] / max_cost) * 100, 2) if max_cost > 0 else 0,
        round((stats['avg_current_cost'] / stats['avg_optimal_cost']) * 50, 2) if stats['avg_optimal_cost'] > 0 else 0,
        round((current_instance_count / max_instances) * 100, 2) if max_instances > 0 else 0,
        100,  # Current cluster count is baseline
        50  # Current efficiency baseline
    ]

    optimal_data = [
        round((stats['total_optimal_cost'] / max_cost) * 100, 2) if max_cost > 0 else 0,
        50,  # Optimal avg cost is baseline
        round((optimal_instance_count / max_instances) * 100, 2) if max_instances > 0 else 0,
        100,  # Same cluster count
        round(((stats['total_current_cost'] - stats['total_optimal_cost']) / stats['total_current_cost']) * 100, 2) if stats['total_current_cost'] > 0 else 0
    ]

    db.close()
    return jsonify({
        'labels': labels,
        'current': current_data,
        'optimal': optimal_data
    })


# ============================================================================
# NEW CHART APIs - COST BREAKDOWN
# ============================================================================

@app.route('/api/charts/cost-treemap')
def api_cost_treemap():
    """API: Get cost components treemap data."""
    import json
    db = AADatabase(DB_PATH)

    run_id = request.args.get('run_id', type=int)

    if not run_id:
        latest = db.conn.execute('SELECT run_id FROM runs WHERE status = "completed" ORDER BY run_timestamp DESC LIMIT 1').fetchone()
        run_id = latest['run_id'] if latest else None

    if not run_id:
        db.close()
        return jsonify({'data': []})

    # Get hierarchical data: Provider -> Region -> Instance Type
    results = db.conn.execute('''
        SELECT
            cm.cloud_provider,
            cm.region,
            cs.infra_json,
            cs.total_price as current_price,
            cr.savings_percent
        FROM cluster_results cr
        JOIN cluster_singles cs ON cr.result_id = cs.result_id AND cs.cluster_type = 'current'
        LEFT JOIN cluster_metadata cm ON cr.mc_uid = cm.mc_uid
        WHERE cr.run_id = ? AND cr.status = 'success'
    ''', (run_id,)).fetchall()

    # Build hierarchical structure
    hierarchy = {}

    for row in results:
        provider = row['cloud_provider'] or 'Unknown'
        region = row['region'] or 'Unknown'
        infra = json.loads(row['infra_json'])

        if provider not in hierarchy:
            hierarchy[provider] = {}

        if region not in hierarchy[provider]:
            hierarchy[provider][region] = {}

        # Get primary instance type
        if infra:
            primary_instance = max(infra.items(), key=lambda x: x[1])[0]

            if primary_instance not in hierarchy[provider][region]:
                hierarchy[provider][region][primary_instance] = {
                    'cost': 0,
                    'savings_percent': 0,
                    'count': 0
                }

            hierarchy[provider][region][primary_instance]['cost'] += row['current_price']
            hierarchy[provider][region][primary_instance]['savings_percent'] += row['savings_percent']
            hierarchy[provider][region][primary_instance]['count'] += 1

    # Convert to treemap format
    treemap_data = []
    for provider, regions in hierarchy.items():
        for region, instances in regions.items():
            for instance_type, data in instances.items():
                avg_savings = data['savings_percent'] / data['count'] if data['count'] > 0 else 0
                treemap_data.append({
                    'provider': provider,
                    'region': region,
                    'instance_type': instance_type,
                    'cost': round(data['cost'], 2),
                    'savings_percent': round(avg_savings, 2),
                    'count': data['count']
                })

    db.close()
    return jsonify({'data': treemap_data})


# ============================================================================
# NEW OPERATIONAL CHARTS APIs
# ============================================================================

@app.route('/api/charts/cluster-age-savings-potential')
def api_cluster_age_savings_potential():
    """API: Get cluster age vs savings potential scatter plot data."""
    from datetime import datetime
    db = AADatabase(DB_PATH)

    run_id = request.args.get('run_id', type=int)
    cloud_provider = request.args.get('cloudProvider', default='All')
    software_version = request.args.get('softwareVersion', default='All')

    if not run_id:
        latest = db.conn.execute('SELECT run_id FROM runs WHERE status = "completed" ORDER BY run_timestamp DESC LIMIT 1').fetchone()
        run_id = latest['run_id'] if latest else None

    if not run_id:
        db.close()
        return jsonify({'data': []})

    # Build filter clause
    filter_clauses, filter_params = build_filter_clause(cloud_provider, software_version)
    where_clauses = ['cr.run_id = ?', 'cr.status = "success"', 'cr.total_savings > 0'] + filter_clauses
    where_clause = ' AND '.join(where_clauses)
    params = [run_id] + filter_params

    # Get clusters with age and savings data
    query = '''
        SELECT
            cr.mc_uid,
            cr.total_savings,
            cr.savings_percent,
            cm.creation_date
        FROM cluster_results cr
        LEFT JOIN cluster_metadata cm ON cr.mc_uid = cm.mc_uid
        WHERE {}
        AND cm.creation_date IS NOT NULL
    '''.format(where_clause)
    results = db.conn.execute(query, tuple(params)).fetchall()

    # Calculate age and prepare data
    current_date = datetime.now()
    scatter_data = []

    for row in results:
        try:
            creation_date = datetime.fromisoformat(row['creation_date'].replace('Z', '+00:00'))
            age_days = (current_date - creation_date).days

            scatter_data.append({
                'x': age_days,
                'y': round(row['total_savings'], 2),
                'savings_percent': round(row['savings_percent'], 1),
                'label': row['mc_uid'][:12] + '...'
            })
        except (ValueError, AttributeError):
            continue

    db.close()
    return jsonify({'data': scatter_data})


@app.route('/api/charts/cost-breakdown-by-component')
def api_cost_breakdown_by_component():
    """API: Get cost breakdown by component (instance vs storage) per cloud provider."""
    db = AADatabase(DB_PATH)

    run_id = request.args.get('run_id', type=int)
    software_version = request.args.get('softwareVersion', default='All')

    if not run_id:
        latest = db.conn.execute('SELECT run_id FROM runs WHERE status = "completed" ORDER BY run_timestamp DESC LIMIT 1').fetchone()
        run_id = latest['run_id'] if latest else None

    if not run_id:
        db.close()
        return jsonify({'labels': [], 'instance_costs': [], 'storage_costs': []})

    # Build filter clause (no cloud_provider filter since we're grouping by it)
    filter_clauses = []
    filter_params = []

    if software_version != 'All':
        filter_clauses.append('cm.software_version = ?')
        filter_params.append(software_version)

    where_clauses = ['cr.run_id = ?', 'cr.status = "success"'] + filter_clauses
    where_clause = ' AND '.join(where_clauses)
    params = [run_id] + filter_params

    # Get cost breakdown by cloud provider
    query = '''
        SELECT
            cm.cloud_provider,
            SUM(cs.instance_price) as total_instance_cost,
            SUM(cs.storage_price) as total_storage_cost
        FROM cluster_results cr
        JOIN cluster_singles cs ON cr.result_id = cs.result_id AND cs.cluster_type = 'current'
        LEFT JOIN cluster_metadata cm ON cr.mc_uid = cm.mc_uid
        WHERE {}
        AND cm.cloud_provider IS NOT NULL
        GROUP BY cm.cloud_provider
        ORDER BY (SUM(cs.instance_price) + SUM(cs.storage_price)) DESC
    '''.format(where_clause)
    results = db.conn.execute(query, tuple(params)).fetchall()

    labels = []
    instance_costs = []
    storage_costs = []

    for row in results:
        labels.append(row['cloud_provider'])
        instance_costs.append(round(row['total_instance_cost'], 2))
        storage_costs.append(round(row['total_storage_cost'], 2))

    db.close()
    return jsonify({
        'labels': labels,
        'instance_costs': instance_costs,
        'storage_costs': storage_costs
    })


@app.route('/api/charts/optimization-rate-trend')
def api_optimization_rate_trend():
    """API: Get optimization rate trend over time (last 10 runs)."""
    db = AADatabase(DB_PATH)

    cloud_provider = request.args.get('cloudProvider', default='All')
    software_version = request.args.get('softwareVersion', default='All')

    # Get last 10 completed runs
    runs = db.conn.execute('''
        SELECT run_id, run_timestamp
        FROM runs
        WHERE status = 'completed'
        ORDER BY run_timestamp DESC
        LIMIT 10
    ''').fetchall()

    if not runs:
        db.close()
        return jsonify({'labels': [], 'optimization_rate': [], 'avg_savings_percent': []})

    # Reverse to show oldest first
    runs = list(reversed(runs))

    labels = []
    optimization_rates = []
    avg_savings_percents = []

    for run in runs:
        run_id = run['run_id']

        # Build filter clause
        filter_clauses, filter_params = build_filter_clause(cloud_provider, software_version)
        where_clauses = ['cr.run_id = ?', 'cr.status = "success"'] + filter_clauses
        where_clause = ' AND '.join(where_clauses)
        params = [run_id] + filter_params

        # Calculate optimization rate (% of clusters with savings > 10%)
        query = '''
            SELECT
                COUNT(*) as total_clusters,
                SUM(CASE WHEN cr.savings_percent > 10 THEN 1 ELSE 0 END) as optimizable_clusters,
                AVG(cr.savings_percent) as avg_savings_percent
            FROM cluster_results cr
            LEFT JOIN cluster_metadata cm ON cr.mc_uid = cm.mc_uid
            WHERE {}
        '''.format(where_clause)
        stats = db.conn.execute(query, tuple(params)).fetchone()

        labels.append(run['run_timestamp'][:10])  # Date only

        if stats['total_clusters'] > 0:
            opt_rate = (stats['optimizable_clusters'] / stats['total_clusters']) * 100
            optimization_rates.append(round(opt_rate, 1))
            avg_savings_percents.append(round(stats['avg_savings_percent'] or 0, 1))
        else:
            optimization_rates.append(0)
            avg_savings_percents.append(0)

    db.close()
    return jsonify({
        'labels': labels,
        'optimization_rate': optimization_rates,
        'avg_savings_percent': avg_savings_percents
    })


@app.route('/api/charts/regional-cost-efficiency')
def api_regional_cost_efficiency():
    """API: Get regional cost efficiency matrix (bubble chart data)."""
    db = AADatabase(DB_PATH)

    run_id = request.args.get('run_id', type=int)
    cloud_provider = request.args.get('cloudProvider', default='All')
    software_version = request.args.get('softwareVersion', default='All')

    if not run_id:
        latest = db.conn.execute('SELECT run_id FROM runs WHERE status = "completed" ORDER BY run_timestamp DESC LIMIT 1').fetchone()
        run_id = latest['run_id'] if latest else None

    if not run_id:
        db.close()
        return jsonify({'data': []})

    # Build filter clause (only positive savings)
    filter_clauses, filter_params = build_filter_clause(cloud_provider, software_version)
    where_clauses = ['cr.run_id = ?', 'cr.status = "success"', 'cr.total_savings > 0'] + filter_clauses
    where_clause = ' AND '.join(where_clauses)
    params = [run_id] + filter_params

    # Get data grouped by region and cloud provider
    # Note: Use COUNT(DISTINCT) and subquery to avoid duplication from multiple 'current' configs per cluster
    query = '''
        SELECT
            cm.region,
            cm.cloud_provider,
            COUNT(DISTINCT cr.mc_uid) as cluster_count,
            AVG(cs.total_price) as avg_cost_per_cluster,
            (SELECT SUM(cr2.total_savings)
             FROM cluster_results cr2
             LEFT JOIN cluster_metadata cm2 ON cr2.mc_uid = cm2.mc_uid
             WHERE cr2.run_id = cr.run_id
             AND cr2.status = 'success'
             AND cr2.total_savings > 0
             AND cm2.region = cm.region
             AND cm2.cloud_provider = cm.cloud_provider) as total_savings
        FROM cluster_results cr
        JOIN cluster_singles cs ON cr.result_id = cs.result_id AND cs.cluster_type = 'current'
        LEFT JOIN cluster_metadata cm ON cr.mc_uid = cm.mc_uid
        WHERE {}
        AND cm.region IS NOT NULL
        AND cm.cloud_provider IS NOT NULL
        GROUP BY cm.region, cm.cloud_provider
        HAVING cluster_count > 0
        ORDER BY total_savings DESC
    '''.format(where_clause)
    results = db.conn.execute(query, tuple(params)).fetchall()

    # Prepare bubble chart data
    bubble_data = []

    # Color mapping for providers
    provider_colors = {
        'AWS': 'rgba(255, 153, 0, 0.6)',
        'GCP': 'rgba(66, 133, 244, 0.6)',
        'Azure': 'rgba(0, 120, 212, 0.6)'
    }

    for row in results:
        bubble_data.append({
            'x': row['cluster_count'],
            'y': round(row['avg_cost_per_cluster'], 2),
            'r': max(5, min(50, row['total_savings'] / 1000)),  # Bubble size (5-50 range)
            'label': row['region'],
            'provider': row['cloud_provider'],
            'total_savings': round(row['total_savings'], 2),
            'backgroundColor': provider_colors.get(row['cloud_provider'], 'rgba(128, 128, 128, 0.6)')
        })

    db.close()
    return jsonify({'data': bubble_data})


@app.route('/api/charts/shards-distribution-cost')
def api_shards_distribution_cost():
    """API: Get shards distribution vs cost (box plot data)."""
    db = AADatabase(DB_PATH)

    run_id = request.args.get('run_id', type=int)
    cloud_provider = request.args.get('cloudProvider', default='All')
    software_version = request.args.get('softwareVersion', default='All')

    if not run_id:
        latest = db.conn.execute('SELECT run_id FROM runs WHERE status = "completed" ORDER BY run_timestamp DESC LIMIT 1').fetchone()
        run_id = latest['run_id'] if latest else None

    if not run_id:
        db.close()
        return jsonify({'data': []})

    # Build filter clause
    filter_clauses, filter_params = build_filter_clause(cloud_provider, software_version)
    where_clauses = ['cr.run_id = ?', 'cr.status = "success"'] + filter_clauses
    where_clause = ' AND '.join(where_clauses)
    params = [run_id] + filter_params

    # Get clusters with shards count and cost
    query = '''
        SELECT
            cm.shards_count,
            cs.total_price,
            cr.mc_uid
        FROM cluster_results cr
        JOIN cluster_singles cs ON cr.result_id = cs.result_id AND cs.cluster_type = 'current'
        LEFT JOIN cluster_metadata cm ON cr.mc_uid = cm.mc_uid
        WHERE {}
        AND cm.shards_count IS NOT NULL
        AND cm.shards_count > 0
    '''.format(where_clause)
    results = db.conn.execute(query, tuple(params)).fetchall()

    # Group by shard ranges
    shard_groups = {
        '1-5 shards': [],
        '6-10 shards': [],
        '11-20 shards': [],
        '21+ shards': []
    }

    for row in results:
        shards = row['shards_count']
        cost_per_shard = row['total_price'] / shards if shards > 0 else 0

        if shards <= 5:
            shard_groups['1-5 shards'].append(cost_per_shard)
        elif shards <= 10:
            shard_groups['6-10 shards'].append(cost_per_shard)
        elif shards <= 20:
            shard_groups['11-20 shards'].append(cost_per_shard)
        else:
            shard_groups['21+ shards'].append(cost_per_shard)

    # Calculate box plot statistics for each group
    box_plot_data = []

    for group_name, costs in shard_groups.items():
        if not costs:
            continue

        costs.sort()
        n = len(costs)

        q1_idx = n // 4
        q2_idx = n // 2
        q3_idx = (3 * n) // 4

        q1 = costs[q1_idx]
        q2 = costs[q2_idx]  # Median
        q3 = costs[q3_idx]

        box_plot_data.append({
            'group': group_name,
            'min': round(costs[0], 2),
            'q1': round(q1, 2),
            'median': round(q2, 2),
            'q3': round(q3, 2),
            'max': round(costs[-1], 2),
            'count': n
        })

    db.close()
    return jsonify({'data': box_plot_data})


@app.route('/api/charts/optimization-priority')
def api_optimization_priority():
    """API: Get top 10 clusters by optimization priority score."""
    from datetime import datetime
    db = AADatabase(DB_PATH)

    run_id = request.args.get('run_id', type=int)
    cloud_provider = request.args.get('cloudProvider', default='All')
    software_version = request.args.get('softwareVersion', default='All')

    if not run_id:
        latest = db.conn.execute('SELECT run_id FROM runs WHERE status = "completed" ORDER BY run_timestamp DESC LIMIT 1').fetchone()
        run_id = latest['run_id'] if latest else None

    if not run_id:
        db.close()
        return jsonify({'labels': [], 'scores': [], 'colors': []})

    # Build filter clause
    filter_clauses, filter_params = build_filter_clause(cloud_provider, software_version)
    where_clauses = ['cr.run_id = ?', 'cr.status = "success"', 'cr.total_savings > 0'] + filter_clauses
    where_clause = ' AND '.join(where_clauses)
    params = [run_id] + filter_params

    # Get clusters with all necessary data
    query = '''
        SELECT
            cr.mc_uid,
            cr.total_savings,
            cr.savings_percent,
            cs.total_price as current_cost,
            cm.creation_date
        FROM cluster_results cr
        JOIN cluster_singles cs ON cr.result_id = cs.result_id AND cs.cluster_type = 'current'
        LEFT JOIN cluster_metadata cm ON cr.mc_uid = cm.mc_uid
        WHERE {}
    '''.format(where_clause)
    results = db.conn.execute(query, tuple(params)).fetchall()

    # Calculate priority scores
    current_date = datetime.now()
    clusters_with_scores = []

    for row in results:
        # Calculate age factor
        age_factor = 0
        if row['creation_date']:
            try:
                creation_date = datetime.fromisoformat(row['creation_date'].replace('Z', '+00:00'))
                age_days = (current_date - creation_date).days
                age_factor = age_days / 365  # Years
            except (ValueError, AttributeError):
                age_factor = 0

        # Priority Score Formula: (savings_$ × 0.4) + (savings_% × 0.3) + (age_years × 0.2) + (current_cost × 0.1)
        # Normalize to 0-100 scale
        savings_score = min(100, (row['total_savings'] / 10000) * 100) * 0.4
        percent_score = min(100, row['savings_percent']) * 0.3
        age_score = min(100, age_factor * 20) * 0.2
        cost_score = min(100, (row['current_cost'] / 10000) * 100) * 0.1

        priority_score = savings_score + percent_score + age_score + cost_score

        clusters_with_scores.append({
            'mc_uid': row['mc_uid'],
            'priority_score': priority_score,
            'total_savings': row['total_savings'],
            'savings_percent': row['savings_percent']
        })

    # Sort by priority score and get top 10
    clusters_with_scores.sort(key=lambda x: x['priority_score'], reverse=True)
    top_10 = clusters_with_scores[:10]

    labels = []
    scores = []
    colors = []

    for cluster in top_10:
        labels.append(cluster['mc_uid'][:12] + '...')
        scores.append(round(cluster['priority_score'], 1))

        # Color based on urgency
        if cluster['priority_score'] >= 70:
            colors.append('rgba(220, 53, 69, 0.8)')  # Red - High priority
        elif cluster['priority_score'] >= 40:
            colors.append('rgba(255, 193, 7, 0.8)')  # Yellow - Medium priority
        else:
            colors.append('rgba(40, 167, 69, 0.8)')  # Green - Low priority

    db.close()
    return jsonify({
        'labels': labels,
        'scores': scores,
        'colors': colors
    })


# ============================================================================
# FILTER APIs
# ============================================================================

@app.route('/api/filters/cloud-providers')
def api_filter_cloud_providers():
    """API: Get list of cloud providers for filter."""
    db = AADatabase(DB_PATH)

    run_id = request.args.get('run_id', type=int)

    if not run_id:
        latest = db.conn.execute('SELECT run_id FROM runs WHERE status = "completed" ORDER BY run_timestamp DESC LIMIT 1').fetchone()
        run_id = latest['run_id'] if latest else None

    if not run_id:
        db.close()
        return jsonify({'providers': []})

    # Get unique cloud providers for this run
    results = db.conn.execute('''
        SELECT DISTINCT cm.cloud_provider
        FROM cluster_results cr
        LEFT JOIN cluster_metadata cm ON cr.mc_uid = cm.mc_uid
        WHERE cr.run_id = ? AND cr.status = 'success' AND cm.cloud_provider IS NOT NULL
        ORDER BY cm.cloud_provider
    ''', (run_id,)).fetchall()

    providers = [row['cloud_provider'] for row in results]

    db.close()
    return jsonify({'providers': providers})


@app.route('/api/filters/software-versions')
def api_filter_software_versions():
    """API: Get list of Software versions for filter."""
    db = AADatabase(DB_PATH)

    run_id = request.args.get('run_id', type=int)

    if not run_id:
        latest = db.conn.execute('SELECT run_id FROM runs WHERE status = "completed" ORDER BY run_timestamp DESC LIMIT 1').fetchone()
        run_id = latest['run_id'] if latest else None

    if not run_id:
        db.close()
        return jsonify({'versions': []})

    # Get unique Software versions for this run (with fallback to redis_version)
    results = db.conn.execute('''
        SELECT DISTINCT COALESCE(cm.software_version, cm.redis_version) as version
        FROM cluster_results cr
        LEFT JOIN cluster_metadata cm ON cr.mc_uid = cm.mc_uid
        WHERE cr.run_id = ? AND cr.status = 'success' AND COALESCE(cm.software_version, cm.redis_version) IS NOT NULL
        ORDER BY version DESC
    ''', (run_id,)).fetchall()

    versions = [row['version'] for row in results]

    db.close()
    return jsonify({'versions': versions})


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    """404 error handler."""
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_error(error):
    """500 error handler."""
    return render_template('500.html'), 500


# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    print("=" * 80)
    print("AA Report Web UI")
    print("=" * 80)
    print(f"Database: {DB_PATH}")
    print("Starting Flask server...")
    print("Open browser at: http://localhost:5000")
    print("=" * 80)

    # Use environment variable for debug mode and host
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() in ('true', '1', 'yes')
    host = os.environ.get('FLASK_HOST', '127.0.0.1')  # Default to localhost only
    port = int(os.environ.get('FLASK_PORT', '5000'))

    if debug_mode:
        logger.warning("WARNING: Running in DEBUG mode - DO NOT use in production!")
    if host == '0.0.0.0':
        logger.warning("WARNING: Server accessible from all network interfaces!")

    app.run(debug=debug_mode, host=host, port=port)

