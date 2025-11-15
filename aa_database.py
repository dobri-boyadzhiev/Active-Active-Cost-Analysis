#!/usr/bin/env python3
"""
AA Report Database - SQLite storage for cluster optimization results.
See README.md for schema details.
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
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(Path.home() / 'aa_report_cache.db')
        self.db_path = db_path
        self.conn = None
        self._connect()
        self._create_schema()
        logger.info(f"Database: {self.db_path}")

    def _connect(self):
        self.conn = sqlite3.connect(self.db_path, timeout=30.0)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode=WAL")
    
    def _create_schema(self):
        cursor = self.conn.cursor()
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
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cluster_singles (
                single_id INTEGER PRIMARY KEY AUTOINCREMENT,
                result_id INTEGER NOT NULL,
                cluster_uid TEXT NOT NULL,
                cluster_type TEXT NOT NULL,
                infra_json TEXT NOT NULL,
                instance_price REAL NOT NULL,
                storage_price REAL NOT NULL,
                total_price REAL NOT NULL,
                total_instances INTEGER,
                FOREIGN KEY (result_id) REFERENCES cluster_results(result_id)
            )
        ''')
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
                -- New fields
                creation_date TEXT,
                shards_count INTEGER,
                max_shards_count INTEGER,
                total_storage_gb INTEGER,
                data_nodes_count INTEGER,
                quorum_nodes_count INTEGER,
                total_nodes_count INTEGER,
                os_version TEXT,
                software_version TEXT,
                rof_enabled INTEGER,
                -- Timestamps
                created_at TEXT,
                last_updated TEXT
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_runs_timestamp ON runs(run_timestamp DESC)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cluster_results_mc_uid ON cluster_results(mc_uid)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cluster_results_run_id ON cluster_results(run_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cluster_results_savings ON cluster_results(total_savings DESC)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cluster_metadata_provider ON cluster_metadata(cloud_provider)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cluster_metadata_region ON cluster_metadata(region)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cluster_results_run_status ON cluster_results(run_id, status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cluster_singles_result_type ON cluster_singles(result_id, cluster_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_runs_status_timestamp ON runs(status, run_timestamp DESC)')
        self.conn.commit()
    
    @contextmanager
    def transaction(self):
        try:
            yield self.conn
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Transaction failed: {e}")
            raise

    def create_run(self, jira_ticket: str, total_clusters: int) -> int:
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO runs (run_timestamp, jira_ticket, total_clusters, status)
            VALUES (?, ?, ?, 'in_progress')
        ''', (datetime.datetime.now().isoformat(), jira_ticket, total_clusters))
        self.conn.commit()
        run_id = cursor.lastrowid
        logger.info(f"Run created: {run_id}")
        return run_id

    def is_cluster_processed(self, run_id: int, mc_uid: str) -> bool:
        cursor = self.conn.cursor()
        cursor.execute('SELECT status FROM cluster_results WHERE run_id = ? AND mc_uid = ?', (run_id, mc_uid))
        row = cursor.fetchone()
        return row and row['status'] == 'success'
    
    def save_cluster_result(self, run_id: int, result) -> None:
        with self.transaction():
            cursor = self.conn.cursor()
            total_current = sum(c.price.total for c, _ in result.clusters)
            total_optimal = sum(o.price.total for _, o in result.clusters)
            total_savings = total_current - total_optimal
            savings_percent = (total_savings / total_current * 100) if total_current > 0 else 0

            cursor.execute('''
                INSERT OR REPLACE INTO cluster_results
                (run_id, mc_uid, processed_at, status, total_savings, savings_percent)
                VALUES (?, ?, ?, 'success', ?, ?)
            ''', (run_id, result.uid, datetime.datetime.now().isoformat(), total_savings, savings_percent))
            result_id = cursor.lastrowid

            for current, optimal in result.clusters:
                cursor.execute('''
                    INSERT INTO cluster_singles
                    (result_id, cluster_uid, cluster_type, infra_json,
                     instance_price, storage_price, total_price, total_instances)
                    VALUES (?, ?, 'current', ?, ?, ?, ?, ?)
                ''', (result_id, current.uid, json.dumps(current.infra),
                      current.price.instance, current.price.storage,
                      current.price.total, sum(current.infra.values())))

                cursor.execute('''
                    INSERT INTO cluster_singles
                    (result_id, cluster_uid, cluster_type, infra_json,
                     instance_price, storage_price, total_price, total_instances)
                    VALUES (?, ?, 'optimal', ?, ?, ?, ?, ?)
                ''', (result_id, optimal.uid, json.dumps(optimal.infra),
                      optimal.price.instance, optimal.price.storage,
                      optimal.price.total, sum(optimal.infra.values())))

    def save_cluster_metadata(self, mc_uid: str, cluster_name: str = None,
                             cloud_provider: str = None, region: str = None,
                             account_id: str = None, redis_version: str = None,
                             multi_az: bool = None, availability_zones: str = None,
                             storage_type: str = None,
                             # New parameters
                             creation_date: str = None, shards_count: int = None,
                             max_shards_count: int = None, total_storage_gb: int = None,
                             data_nodes_count: int = None, quorum_nodes_count: int = None,
                             total_nodes_count: int = None, os_version: str = None,
                             software_version: str = None, rof_enabled: bool = None) -> None:
        with self.transaction():
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO cluster_metadata
                (mc_uid, cluster_name, cloud_provider, region, account_id,
                 redis_version, multi_az, availability_zones, storage_type,
                 creation_date, shards_count, max_shards_count, total_storage_gb,
                 data_nodes_count, quorum_nodes_count, total_nodes_count,
                 os_version, software_version, rof_enabled, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (mc_uid, cluster_name, cloud_provider, region, account_id,
                  redis_version, 1 if multi_az else 0 if multi_az is not None else None,
                  availability_zones, storage_type,
                  creation_date, shards_count, max_shards_count, total_storage_gb,
                  data_nodes_count, quorum_nodes_count, total_nodes_count,
                  os_version, software_version, 1 if rof_enabled else 0 if rof_enabled is not None else None,
                  datetime.datetime.now().isoformat()))

    def load_cluster_result(self, run_id: int, mc_uid: str) -> Optional[Dict]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT result_id FROM cluster_results WHERE run_id = ? AND mc_uid = ? AND status = ?',
                      (run_id, mc_uid, 'success'))
        row = cursor.fetchone()
        if not row:
            return None

        cursor.execute('''
            SELECT cluster_uid, cluster_type, infra_json, instance_price, storage_price, total_price
            FROM cluster_singles WHERE result_id = ? ORDER BY single_id
        ''', (row['result_id'],))

        cluster_map = {}
        for single in cursor.fetchall():
            uid = single['cluster_uid']
            cluster_data = {
                'uid': uid,
                'infra': json.loads(single['infra_json']),
                'price': {'instance': single['instance_price'], 'storage': single['storage_price'],
                         'total': single['total_price']}
            }
            if uid not in cluster_map:
                cluster_map[uid] = {}
            cluster_map[uid][single['cluster_type']] = cluster_data

        clusters = [(data['current'], data['optimal']) for uid, data in cluster_map.items()
                   if 'current' in data and 'optimal' in data]
        return {'uid': mc_uid, 'clusters': clusters}

    def mark_cluster_failed(self, run_id: int, mc_uid: str, error_message: str) -> None:
        with self.transaction():
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO cluster_results
                (run_id, mc_uid, processed_at, status, error_message)
                VALUES (?, ?, ?, 'failed', ?)
            ''', (run_id, mc_uid, datetime.datetime.now().isoformat(), error_message))

    def update_run_statistics(self, run_id: int) -> Dict[str, int]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT
                COUNT(CASE WHEN status = 'success' THEN 1 END) as processed,
                COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed
            FROM cluster_results WHERE run_id = ?
        ''', (run_id,))
        row = cursor.fetchone()
        processed, failed = row['processed'], row['failed']
        cursor.execute('UPDATE runs SET processed_clusters = ?, failed_clusters = ? WHERE run_id = ?',
                      (processed, failed, run_id))
        self.conn.commit()
        return {'processed': processed, 'failed': failed}

    def complete_run(self, run_id: int, csv_path: str = None) -> None:
        self.update_run_statistics(run_id)
        cursor = self.conn.cursor()
        cursor.execute('UPDATE runs SET status = ?, completed_at = ?, csv_path = ? WHERE run_id = ?',
                      ('completed', datetime.datetime.now().isoformat(), csv_path, run_id))
        self.conn.commit()
        logger.info(f"Run {run_id} completed")

    def get_all_results_for_run(self, run_id: int) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT cr.mc_uid, cs.cluster_uid, cs.cluster_type, cs.infra_json,
                   cs.instance_price, cs.storage_price, cs.total_price
            FROM cluster_results cr
            JOIN cluster_singles cs ON cr.result_id = cs.result_id
            WHERE cr.run_id = ? AND cr.status = 'success'
            ORDER BY cr.processed_at, cs.single_id
        ''', (run_id,))

        results_map = {}
        for row in cursor.fetchall():
            mc_uid = row['mc_uid']
            if mc_uid not in results_map:
                results_map[mc_uid] = {'uid': mc_uid, 'cluster_map': {}}

            cluster_uid = row['cluster_uid']
            cluster_data = {
                'uid': cluster_uid,
                'infra': json.loads(row['infra_json']),
                'price': {'instance': row['instance_price'], 'storage': row['storage_price'],
                         'total': row['total_price']}
            }
            if cluster_uid not in results_map[mc_uid]['cluster_map']:
                results_map[mc_uid]['cluster_map'][cluster_uid] = {}
            results_map[mc_uid]['cluster_map'][cluster_uid][row['cluster_type']] = cluster_data

        results = []
        for mc_uid, data in results_map.items():
            clusters = [(types['current'], types['optimal'])
                       for uid, types in data['cluster_map'].items()
                       if 'current' in types and 'optimal' in types]
            results.append({'uid': mc_uid, 'clusters': clusters})
        return results

    def get_cluster_history(self, mc_uid: str, limit: int = 10) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT r.run_timestamp AS timestamp, r.jira_ticket,
                   cr.total_savings AS savings, cr.savings_percent, cr.result_id
            FROM cluster_results cr
            JOIN runs r ON cr.run_id = r.run_id
            WHERE cr.mc_uid = ? AND cr.status = 'success'
            ORDER BY r.run_timestamp DESC LIMIT ?
        ''', (mc_uid, limit))

        history = []
        for row in cursor.fetchall():
            cursor.execute('''
                SELECT
                    SUM(CASE WHEN cluster_type = 'current' THEN total_price ELSE 0 END) as current_price,
                    SUM(CASE WHEN cluster_type = 'optimal' THEN total_price ELSE 0 END) as optimal_price
                FROM cluster_singles WHERE result_id = ?
            ''', (row['result_id'],))
            prices = cursor.fetchone()
            history.append({
                'timestamp': row['timestamp'],
                'jira_ticket': row['jira_ticket'],
                'current_price': round(prices['current_price'] or 0, 2),
                'optimal_price': round(prices['optimal_price'] or 0, 2),
                'savings': round(row['savings'], 2),
                'savings_percent': round(row['savings_percent'], 2)
            })
        return history

    def get_total_savings_trend(self, limit: int = 10) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT r.run_timestamp AS timestamp, r.jira_ticket,
                   SUM(cr.total_savings) AS total_savings,
                   SUM(CASE WHEN cs.cluster_type = 'current' THEN cs.total_price ELSE 0 END) as total_current,
                   SUM(CASE WHEN cs.cluster_type = 'optimal' THEN cs.total_price ELSE 0 END) as total_optimal
            FROM runs r
            JOIN cluster_results cr ON r.run_id = cr.run_id
            JOIN cluster_singles cs ON cr.result_id = cs.result_id
            WHERE r.status = 'completed' AND cr.status = 'success' AND cr.total_savings > 0
            GROUP BY r.run_id ORDER BY r.run_timestamp DESC LIMIT ?
        ''', (limit,))

        trend = []
        for row in cursor.fetchall():
            tc, to, ts = row['total_current'] or 0, row['total_optimal'] or 0, row['total_savings'] or 0
            trend.append({
                'timestamp': row['timestamp'],
                'jira_ticket': row['jira_ticket'],
                'total_current': round(tc, 2),
                'total_optimal': round(to, 2),
                'total_savings': round(ts, 2),
                'savings_percent': round((tc - to) / tc * 100, 2) if tc > 0 else 0
            })
        return trend

    def get_top_savings_opportunities(self, run_id: int = None, limit: int = None) -> List[Dict]:
        cursor = self.conn.cursor()
        if run_id is None:
            cursor.execute('SELECT run_id FROM runs WHERE status = ? ORDER BY run_timestamp DESC LIMIT 1',
                          ('completed',))
            row = cursor.fetchone()
            if not row:
                return []
            run_id = row['run_id']

        query = '''
            SELECT cr.mc_uid, cr.total_savings, cr.savings_percent,
                   SUM(CASE WHEN cs.cluster_type = 'current' THEN cs.total_price ELSE 0 END) as current_price,
                   SUM(CASE WHEN cs.cluster_type = 'optimal' THEN cs.total_price ELSE 0 END) as optimal_price,
                   cm.cloud_provider, COALESCE(cm.software_version, cm.redis_version) as software_version,
                   cm.cluster_name, cm.region, cm.creation_date
            FROM cluster_results cr
            JOIN cluster_singles cs ON cr.result_id = cs.result_id
            LEFT JOIN cluster_metadata cm ON cr.mc_uid = cm.mc_uid
            WHERE cr.run_id = ? AND cr.status = 'success'
            GROUP BY cr.mc_uid ORDER BY cr.total_savings DESC
        '''
        cursor.execute(query + ('' if limit is None else ' LIMIT ?'),
                      (run_id, limit) if limit else (run_id,))

        return [{
            'mc_uid': row['mc_uid'],
            'current_price': round(row['current_price'], 2),
            'optimal_price': round(row['optimal_price'], 2),
            'savings': round(row['total_savings'], 2),
            'savings_percent': round(row['savings_percent'], 2),
            'cloud_provider': row['cloud_provider'],
            'software_version': row['software_version'],
            'cluster_name': row['cluster_name'],
            'region': row['region'],
            'creation_date': row['creation_date']
        } for row in cursor.fetchall()]

    def close(self):
        if self.conn:
            self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

