# AA Report Automation Tool

**Version:** 2.0 (Monolithic Architecture)
**Last Updated:** 2025-11-14
**Author:** Redis Cloud Operations Team

---

## 📋 Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Data Models](#data-models)
- [Database Schema](#database-schema)
- [Configuration](#configuration)
- [Deployment](#deployment)
- [Scheduling](#scheduling)
- [Monitoring](#monitoring)
- [Troubleshooting](#troubleshooting)
- [Analysis Tools](#analysis-tools)

---

## 🎯 Overview

AA Report Automation Tool automates the process of analyzing and optimizing Active-Active Redis clusters via RCP API. The system retrieves current configurations, plans optimal configurations, and calculates potential savings.

### Key Features

✅ **Automated Cluster Discovery** - Automatically retrieve all AA clusters
✅ **Blueprint Analysis** - Analyze current configurations
✅ **Optimization Planning** - Plan optimal configurations
✅ **Cost Calculation** - Calculate savings (current vs optimal)
✅ **Historical Tracking** - SQLite database for historical analysis
✅ **Resume Capability** - Resume interrupted runs
✅ **Rate Limiting** - Protection against API throttling
✅ **Monolithic Design** - Simple 3-file architecture

### Technology Stack

- **Language:** Python 3.7+
- **Database:** SQLite 3
- **External API:** RCP Client (rcp_client module)
- **Dependencies:** requests, tabulate

### File Structure

```
rcp/
├── aa_report_automation.py      ← Main script + data models
├── aa_database.py                ← Database layer (shared with web app)
└── README.md                     ← This file (complete documentation)
```

**Note:** `aa_database.py` is shared between the automation script and the Flask web application.

---

## 🚀 Quick Start

### Prerequisites

**System Requirements:**
- Python 3.7+
- 512 MB RAM minimum (1 GB recommended)
- Network access to RCP server (port 443)

**Install Dependencies:**
```bash
pip install requests tabulate
```

**Verify RCP Client:**
```bash
python -c "import rcp_client; print('RCP client available')"
```

### Installation

```bash
# 1. Copy files to server
scp -r rcp/ user@server:/home/user/

# 2. Set permissions
chmod +x aa_report_automation.py

# 3. Set environment variables
export RCP_SERVER="rcp-server-prod.redislabs.com"
export RCP_USERNAME="operations"
export RCP_PASSWORD="your-password-here"
```

### Basic Usage

```bash
# Test with 5 clusters
python aa_report_automation.py --limit 5

# Full run (all clusters)
python aa_report_automation.py

# With debug logging
python aa_report_automation.py --limit 5 --log-level DEBUG
```

### Output

**What gets created:**

1. **Database:** `~/aa_report_cache.db`
   - Stores all optimization results
   - Historical tracking
   - ~1 MB per run with 150 clusters
   - No CSV files, no temporary directories

---

## 🏗️ Architecture

### Monolithic Design

```
aa_report_automation.py (Main Script - 318 lines)
├── Data Models (dataclasses)
│   ├── Price
│   ├── Cluster
│   ├── MultiCluster
│   └── MultiClusterResult
│
├── Configuration
│   └── Config class (environment variables)
│
├── RCP Integration
│   ├── RateLimiter (2 calls/second)
│   └── RCPClientWrapper (API wrapper)
│
├── Report Generation
│   ├── handle_aa_cluster() - Process single cluster
│   └── generate_aa_report() - Main orchestration
│
└── CLI (argparse)
    ├── --limit N (test with N clusters)
    └── --log-level (DEBUG/INFO/WARNING/ERROR)

aa_database.py (Database Layer - 350 lines)
└── AADatabase class
    ├── Schema management (4 tables, 9 indexes)
    ├── CRUD operations
    ├── Transaction handling
    └── Historical analysis queries
```

### Data Flow

```
1. CLI parses arguments (--limit, --log-level)
2. Read credentials from environment (RCP_SERVER, RCP_USERNAME, RCP_PASSWORD)
3. RCPClientWrapper.get_all_multi_clusters() → List of AA clusters
4. For each cluster:
   a. RCPClientWrapper.get_multi_cluster_blueprint() → Current config
   b. RCPClientWrapper.plan_optimal_multi_cluster() → Optimal config
   c. handle_aa_cluster() → Compare & calculate savings
   d. AADatabase.save_cluster_result() → Store in SQLite database
5. Complete run and update statistics
```

---

## 📊 Data Models

### Core Classes (aa_report_automation.py)

#### Price
```python
@dataclass
class Price:
    storage: float    # Storage cost (USD/month)
    instance: float   # Instance cost (USD/month)

    @property
    def total(self) -> float:
        return self.storage + self.instance
```

#### Cluster
```python
@dataclass
class Cluster:
    uid: str                      # Cluster UID
    infra: Dict[str, int]         # {instance_type: count}
    price: Price                  # Pricing info
```

**Example:**
```python
Cluster(
    uid="cluster-12345",
    infra={"m5.large": 3, "m5.xlarge": 2},
    price=Price(storage=100.0, instance=500.0)
)
```

#### MultiCluster
```python
@dataclass
class MultiCluster:
    uid: str                      # Multi-cluster UID
    clusters: List[Cluster]       # List of single clusters
```

#### MultiClusterResult
```python
@dataclass
class MultiClusterResult:
    uid: str                                    # Multi-cluster UID
    clusters: List[Tuple[Cluster, Cluster]]     # [(current, optimal), ...]
```

---

## 💾 Database Schema

### Tables

#### runs (Run Tracking)
```sql
CREATE TABLE runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_timestamp TEXT NOT NULL,
    jira_ticket TEXT,
    total_clusters INTEGER,
    processed_clusters INTEGER DEFAULT 0,
    failed_clusters INTEGER DEFAULT 0,
    status TEXT DEFAULT 'in_progress',
    csv_path TEXT,
    completed_at TEXT
)
```

#### cluster_results (Optimization Results)
```sql
CREATE TABLE cluster_results (
    result_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    mc_uid TEXT NOT NULL,
    processed_at TEXT NOT NULL,
    status TEXT NOT NULL,
    error_message TEXT,
    total_savings REAL,
    savings_percent REAL,
    total_instances INTEGER,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
)
```

#### cluster_singles (Individual Cluster Data)
```sql
CREATE TABLE cluster_singles (
    single_id INTEGER PRIMARY KEY AUTOINCREMENT,
    result_id INTEGER NOT NULL,
    cluster_uid TEXT NOT NULL,
    cluster_type TEXT NOT NULL,  -- 'current' or 'optimal'
    infra_json TEXT NOT NULL,
    instance_price REAL,
    storage_price REAL,
    total_price REAL,
    total_instances INTEGER,
    FOREIGN KEY (result_id) REFERENCES cluster_results(result_id)
)
```

#### cluster_metadata (Cluster Metadata)
```sql
CREATE TABLE cluster_metadata (
    mc_uid TEXT PRIMARY KEY,
    cluster_name TEXT,
    cloud_provider TEXT,
    region TEXT,
    software_version TEXT,      -- New: Software version (replaces redis_version)
    creation_date TEXT,          -- New: Cluster creation date (ISO format)
    redis_version TEXT,          -- Legacy: Kept for backward compatibility
    created_at TEXT              -- Legacy: Kept for backward compatibility
)
```

### Entity-Relationship Diagram

```
runs (1) ──< (N) cluster_results (1) ──< (N) cluster_singles

cluster_metadata (independent, linked by mc_uid)
```

### Indexes

```sql
CREATE INDEX idx_cluster_results_run_id ON cluster_results(run_id);
CREATE INDEX idx_cluster_results_mc_uid ON cluster_results(mc_uid);
CREATE INDEX idx_cluster_results_savings ON cluster_results(total_savings DESC);
CREATE INDEX idx_cluster_singles_result_id ON cluster_singles(result_id);
CREATE INDEX idx_cluster_metadata_cloud ON cluster_metadata(cloud_provider);
CREATE INDEX idx_cluster_metadata_region ON cluster_metadata(region);
CREATE INDEX idx_cluster_metadata_software_version ON cluster_metadata(software_version);
```

---

## ⚙️ Configuration

### Environment Variables (Recommended)

```bash
# Edit ~/.bashrc or ~/.bash_profile
export RCP_SERVER="rcp-server-prod.redislabs.com"
export RCP_USERNAME="operations"
export RCP_PASSWORD="your-password-here"

# Reload
source ~/.bashrc
```

### Configuration in Script

See `aa_report_automation.py` Config class:

```python
class Config:
    # RCP Configuration (from environment variables)
    RCP_SERVER = os.environ.get('RCP_SERVER', 'rcp-server-prod.redislabs.com')
    RCP_USERNAME = os.environ.get('RCP_USERNAME', 'operations')
    RCP_PASSWORD = os.environ.get('RCP_PASSWORD', '')

    # Performance
    API_CALLS_PER_SECOND = 2.0  # Rate limiting
    HTTP_TIMEOUT = 30           # Seconds
    MAX_RETRIES = 3
    RETRY_DELAY = 5

    # Database
    DB_PATH = os.path.expanduser('~/aa_report_cache.db')

    # Excluded clusters
    EXCLUDE_UIDS = []
```

**Security Note:** All credentials are read from environment variables. Never hardcode passwords!

---

## 🚀 Deployment

### Step 1: Copy Files to Server

```bash
# Using SCP
scp -r rcp/ user@server:/home/user/

# Or using Git
cd /home/user
git clone <repository-url>
cd rcp
```

### Step 2: Set Environment Variables

```bash
# Edit ~/.bashrc
export RCP_SERVER="rcp-server-prod.redislabs.com"
export RCP_USERNAME="operations"
export RCP_PASSWORD="your-password-here"

# Reload
source ~/.bashrc
```

### Step 3: Set Permissions

```bash
chmod +x aa_report_automation.py
chmod 644 aa_database.py
```

### Step 4: Test Run

```bash
# Test with 5 clusters
python aa_report_automation.py --limit 5

# Check output
ls -la ~/aa_report_cache.db
```

### Step 5: Production Run

```bash
# Full run
python aa_report_automation.py
```

---

## ⏰ Scheduling

### Cron Job Setup

**Daily run at 2 AM:**
```bash
# Edit crontab
crontab -e

# Add this line (environment variables must be set in ~/.bashrc):
0 2 * * * cd /home/user/rcp && /usr/bin/python3 aa_report_automation.py >> /home/user/logs/aa_report.log 2>&1
```

**Weekly run on Mondays at 6 AM:**
```bash
0 6 * * 1 cd /home/user/rcp && /usr/bin/python3 aa_report_automation.py >> /home/user/logs/aa_report.log 2>&1
```

**With wrapper script:**
```bash
# Create wrapper: /home/user/rcp/run_report.sh
#!/bin/bash
export RCP_SERVER="rcp-server-prod.redislabs.com"
export RCP_USERNAME="operations"
export RCP_PASSWORD="your-password"
cd /home/user/rcp
python3 aa_report_automation.py

# Make executable
chmod +x /home/user/rcp/run_report.sh

# Add to crontab
0 2 * * * /home/user/rcp/run_report.sh >> /home/user/logs/aa_report.log 2>&1
```

### Systemd Service (Alternative)

**Create service file:** `/etc/systemd/system/aa-report.service`
```ini
[Unit]
Description=AA Report Automation
After=network.target

[Service]
Type=oneshot
User=user
WorkingDirectory=/home/user/rcp
Environment="RCP_SERVER=rcp-server-prod.redislabs.com"
Environment="RCP_USERNAME=operations"
Environment="RCP_PASSWORD=your-password"
ExecStart=/usr/bin/python3 aa_report_automation.py
StandardOutput=append:/home/user/logs/aa_report.log
StandardError=append:/home/user/logs/aa_report.log

[Install]
WantedBy=multi-user.target
```

**Create timer:** `/etc/systemd/system/aa-report.timer`
```ini
[Unit]
Description=AA Report Automation Timer
Requires=aa-report.service

[Timer]
OnCalendar=daily
OnCalendar=02:00
Persistent=true

[Install]
WantedBy=timers.target
```

**Enable and start:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable aa-report.timer
sudo systemctl start aa-report.timer

# Check status
sudo systemctl status aa-report.timer
```


---

## 📊 Monitoring

### Check Run Status

**View database runs:**
```bash
sqlite3 ~/aa_report_cache.db "
SELECT
    run_id,
    run_timestamp,
    total_clusters,
    processed_clusters,
    failed_clusters,
    status
FROM runs
ORDER BY run_id DESC
LIMIT 5;
"
```

### Check Database Size

```bash
# Database file size
ls -lh ~/aa_report_cache.db

# Number of runs
sqlite3 ~/aa_report_cache.db "SELECT COUNT(*) FROM runs;"

# Number of cluster results
sqlite3 ~/aa_report_cache.db "SELECT COUNT(*) FROM cluster_results;"
```

### Log Monitoring

```bash
# View recent logs
tail -f /home/user/logs/aa_report.log

# Search for errors
grep -i error /home/user/logs/aa_report.log

# Count processed clusters
grep "Processing mc-" /home/user/logs/aa_report.log | wc -l
```

---

## 🔍 Troubleshooting

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| `ModuleNotFoundError: rcp_client` | RCP client not installed | Contact Redis Cloud Ops team |
| `Authentication failed` | Invalid credentials | Check RCP_PASSWORD environment variable |
| `Database locked` | Another process using DB | Wait or kill process: `pkill -f aa_report` |
| `Permission denied` | Insufficient permissions | `chmod +x aa_report_automation.py` |
| `Network timeout` | RCP server unreachable | Increase HTTP_TIMEOUT in Config |
| `table cluster_metadata has no column named software_version` | Old database schema | Schema auto-updates on first run |

### Debug Mode

```bash
# Enable verbose logging
python aa_report_automation.py --limit 5 --log-level DEBUG 2>&1 | tee debug.log
```

### Database Issues

**Check database integrity:**
```bash
sqlite3 ~/aa_report_cache.db "PRAGMA integrity_check;"
```

**Reset database (if corrupted):**
```bash
# Backup first
cp ~/aa_report_cache.db ~/aa_report_cache.db.backup_$(date +%Y%m%d)

# Delete and recreate
rm ~/aa_report_cache.db

# Run script again (will create new database)
python aa_report_automation.py --limit 5
```

### Network Issues

**Test RCP connectivity:**
```bash
ping rcp-server-prod.redislabs.com

# Test with Python (set environment variables first)
python -c "
import os
from rcp_client import RcpClient
client = RcpClient(
    hostname=os.environ['RCP_SERVER'],
    username=os.environ['RCP_USERNAME'],
    password=os.environ['RCP_PASSWORD']
)
print('Connection successful!')
"
```

---

## 📈 Analysis Tools

### SQL Queries

**Total savings for latest run:**
```bash
sqlite3 ~/aa_report_cache.db "
SELECT SUM(total_savings) as total_savings
FROM cluster_results
WHERE run_id = (SELECT MAX(run_id) FROM runs);
"
```

**Top 10 clusters by savings:**
```bash
sqlite3 ~/aa_report_cache.db "
SELECT mc_uid, total_savings, savings_percent
FROM cluster_results
WHERE run_id = (SELECT MAX(run_id) FROM runs)
ORDER BY total_savings DESC
LIMIT 10;
"
```

**Filter by cloud provider:**
```bash
sqlite3 ~/aa_report_cache.db "
SELECT
    cr.mc_uid,
    cr.total_savings,
    cm.cloud_provider,
    cm.region,
    COALESCE(cm.software_version, cm.redis_version) as version
FROM cluster_results cr
JOIN cluster_metadata cm ON cr.mc_uid = cm.mc_uid
WHERE cm.cloud_provider = 'AWS'
ORDER BY cr.total_savings DESC;
"
```

**Savings trend over time:**
```bash
sqlite3 ~/aa_report_cache.db "
SELECT
    r.run_timestamp,
    SUM(cr.total_savings) as total_savings,
    COUNT(*) as cluster_count
FROM runs r
JOIN cluster_results cr ON r.run_id = cr.run_id
WHERE cr.status = 'success'
GROUP BY r.run_id
ORDER BY r.run_timestamp DESC
LIMIT 10;
"
```

---

## 🗄️ Database Maintenance

### Backup

**Manual backup:**
```bash
# Create backup
cp ~/aa_report_cache.db ~/aa_report_cache.db.backup_$(date +%Y%m%d)

# Verify backup
ls -lh ~/aa_report_cache.db*
```

**Automated backup (cron):**
```bash
# Add to crontab (daily at 1 AM)
0 1 * * * cp ~/aa_report_cache.db ~/backups/aa_report_cache.db.$(date +\%Y\%m\%d)
```

### Cleanup Old Data

**Delete runs older than 90 days:**
```bash
sqlite3 ~/aa_report_cache.db "
DELETE FROM runs
WHERE run_timestamp < datetime('now', '-90 days');
"
```

**Vacuum database (reclaim space):**
```bash
sqlite3 ~/aa_report_cache.db "VACUUM;"
```

---

## 📚 Additional Resources

### Documentation

- **README.md** (this file) - Complete user guide and reference
- Code is self-documenting with minimal inline comments

### Key Components

**Main Script (aa_report_automation.py):**
- **Data Models** - Price, Cluster, MultiCluster, MultiClusterResult (dataclasses)
- **Config** - Environment-based configuration
- **RateLimiter** - API rate limiting (2 calls/second)
- **RCPClientWrapper** - RCP API integration with retry logic
- **handle_aa_cluster()** - Process single cluster optimization
- **generate_aa_report()** - Main orchestration function

**Database Layer (aa_database.py):**
- **AADatabase** - SQLite wrapper with transaction support
- **Schema management** - 4 tables, 9 indexes
- **CRUD operations** - Save/query cluster results
- **Historical analysis** - Query past optimization runs

### Performance Metrics

**Typical Performance:**
- 150 clusters: ~15-20 minutes
- Rate: ~8-10 clusters/minute
- Database size: ~1 MB per run

**Bottlenecks:**
- RCP API response time (2-3 sec per cluster)
- Rate limiting (2 calls/sec)
- Network latency

---

## 📞 Support

**For questions or issues:**
- Review this documentation
- Review logs with debug mode (`--log-level DEBUG`)
- Check database with SQLite queries
- Contact Redis Cloud Operations team
- Email: dobri.boyadzhiev@redis.com

---

## ✅ Deployment Checklist

- [ ] Python 3.7+ installed
- [ ] Dependencies installed (`requests`, `tabulate`)
- [ ] RCP client module available
- [ ] Files copied to server (aa_report_automation.py, aa_database.py)
- [ ] Permissions set correctly (`chmod +x aa_report_automation.py`)
- [ ] Environment variables configured (RCP_SERVER, RCP_USERNAME, RCP_PASSWORD)
- [ ] Test run successful (`python aa_report_automation.py --limit 5`)
- [ ] Database created successfully (`~/aa_report_cache.db`)
- [ ] Cron job or systemd service configured
- [ ] Monitoring set up
- [ ] Backup strategy in place
- [ ] Documentation reviewed

---

## 📜 License

Internal use only - Redis Ltd.

---

**End of Documentation**


