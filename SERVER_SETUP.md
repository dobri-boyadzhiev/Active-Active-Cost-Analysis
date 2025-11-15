# Active-Active Cost Analysis - Server Setup Guide
# Complete Server Setup Documentation

## Overview

This document describes how to setup and maintain AA Cost Analysis automation on production server.

**Server:** `ip-10-0-0-88`
**Location:** `/opt/active-active-cost-analysis/`
**Virtual Environment:** `/var/vault-users-python3.11-env/`
**GCS Bucket:** `gs://active-active-cost-analysis/`

---

## Initial Setup (One-time setup)

### Step 1: Create Directory

```bash
sudo mkdir -p /opt/active-active-cost-analysis/logs
```

### Step 2: Copy Files

```bash
# From development directory
cd ~/path/to/project

# Copy all files
sudo cp aa_report_automation.py /opt/active-active-cost-analysis/
sudo cp aa_database.py /opt/active-active-cost-analysis/
sudo cp requirements.txt /opt/active-active-cost-analysis/
sudo cp run_aa_report_with_creds.sh /opt/active-active-cost-analysis/
```

### Step 3: Configure Wrapper Script with Credentials

```bash
# Edit wrapper script
sudo nano /opt/active-active-cost-analysis/run_aa_report_with_creds.sh

# Find this line (around line 20):
# export RCP_PASSWORD="YOUR_PASSWORD_HERE"

# Replace with actual password:
# export RCP_PASSWORD="actual_rcp_password"

# Save and exit (Ctrl+O, Enter, Ctrl+X)
```

### Step 4: Make Wrapper Executable and Secure It

```bash
# Make executable
sudo chmod 700 /opt/active-active-cost-analysis/run_aa_report_with_creds.sh

# Check permissions
ls -la /opt/active-active-cost-analysis/run_aa_report_with_creds.sh
# Should see: -rwx------ 1 root root ... run_aa_report_with_creds.sh
```

### Step 5: Test

```bash
# Test with 1 cluster
cd /opt/active-active-cost-analysis
sudo ./run_aa_report_with_creds.sh --limit 1

# Check logs
tail -f /opt/active-active-cost-analysis/logs/aa_report_automation_*.log

# Check database
ls -lh /opt/active-active-cost-analysis/aa_report_cache.db

# Check GCS upload
gsutil ls gs://active-active-cost-analysis/
```

---

## Cron Job Setup

### Configure Automatic Execution

```bash
# Open crontab (as root)
sudo crontab -e

# Add this line for daily execution at 7:00 UTC:
0 7 * * * /opt/active-active-cost-analysis/run_aa_report_with_creds.sh >> /opt/active-active-cost-analysis/logs/cron.log 2>&1
```

### Other Useful Schedules

```bash
# Daily at 2:00 UTC
0 2 * * * /opt/active-active-cost-analysis/run_aa_report_with_creds.sh >> /opt/active-active-cost-analysis/logs/cron.log 2>&1

# Daily at 7:00 UTC
0 7 * * * /opt/active-active-cost-analysis/run_aa_report_with_creds.sh >> /opt/active-active-cost-analysis/logs/cron.log 2>&1

# Every Monday at 7:00 UTC
0 7 * * 1 /opt/active-active-cost-analysis/run_aa_report_with_creds.sh >> /opt/active-active-cost-analysis/logs/cron.log 2>&1
```

### For Bulgaria Time (EET/EEST)

```bash
# Add at the beginning of crontab:
TZ=Europe/Sofia

# Then add the job:
0 7 * * * /opt/active-active-cost-analysis/run_aa_report_with_creds.sh >> /opt/active-active-cost-analysis/logs/cron.log 2>&1
```

### Check Cron Jobs

```bash
# View active cron jobs
sudo crontab -l

# Check cron logs
grep CRON /var/log/syslog | tail -20

# Check application logs
tail -f /opt/active-active-cost-analysis/logs/cron.log
```

---

## File Structure

```
/opt/active-active-cost-analysis/
├── aa_report_automation.py         # Main Python script
├── aa_database.py                  # Database layer
├── requirements.txt                # Python dependencies (minimal)
├── run_aa_report_with_creds.sh     # Wrapper script with credentials (chmod 700)
├── aa_report_cache.db              # SQLite database (auto-created)
└── logs/                           # Logs directory
    ├── aa_report_automation_2025-11-14.log
    └── cron.log
```

---

## Configuration

### Wrapper Script Configuration

All settings are in `run_aa_report_with_creds.sh`:

```bash
# RCP Server Configuration
export RCP_SERVER="rcp-server-prod.redislabs.com"
export RCP_USERNAME="operations"
export RCP_PASSWORD="your_password_here"  # ⚠️ SET THIS!

# GCS Configuration
export GCS_BUCKET_NAME="active-active-cost-analysis"
export ENABLE_GCS_UPLOAD="true"

# Paths
VENV_PATH="/var/vault-users-python3.11-env"
SCRIPT_DIR="/opt/active-active-cost-analysis"
```

### Virtual Environment

The script uses a shared virtual environment:
- **Path:** `/var/vault-users-python3.11-env/`
- **Owner:** `EranCahana:ops`
- **Contains:** `rcp_client`, `rcp_api_client`, `rcp_cli` and other RCP libraries

**Important:** The wrapper script automatically activates venv, no need to do it manually!

---

## Security & Permissions

### Recommended Permissions

```bash
# Wrapper script (contains credentials)
-rwx------ 1 root root  run_aa_report_with_creds.sh  # chmod 700

# Python scripts (no credentials)
-rw-r--r-- 1 root root  aa_report_automation.py      # chmod 644
-rw-r--r-- 1 root root  aa_database.py               # chmod 644

# Database (may contain sensitive data)
-rw-r--r-- 1 root root  aa_report_cache.db           # chmod 644

# Logs directory
drwxr-xr-x 2 root root  logs/                        # chmod 755
```

### GCS Authentication

The script uses **user credentials** (not service account):

1. Temporarily removes `GOOGLE_APPLICATION_CREDENTIALS` env var
2. Uses credentials from `gcloud auth` (user credentials)
3. Uploads database with `gsutil cp`
4. Restores `GOOGLE_APPLICATION_CREDENTIALS`

```bash
# Check user credentials
gcloud auth list

# Check GCS access
gsutil ls gs://active-active-cost-analysis/
```

---

## Monitoring and Logs

### Log Files

```bash
# Daily application logs
/opt/active-active-cost-analysis/logs/aa_report_automation_YYYY-MM-DD.log

# Cron execution logs
/opt/active-active-cost-analysis/logs/cron.log

# System cron logs
/var/log/syslog  # grep CRON
```

### Check Last Execution

```bash
# View recent logs
tail -100 /opt/active-active-cost-analysis/logs/aa_report_automation_*.log

# View cron logs
tail -50 /opt/active-active-cost-analysis/logs/cron.log

# Check database size
ls -lh /opt/active-active-cost-analysis/aa_report_cache.db

# Check GCS upload timestamp
gsutil ls -l gs://active-active-cost-analysis/aa_report_cache.db
```

### Check Database Content

```bash
# Enter database
sqlite3 /opt/active-active-cost-analysis/aa_report_cache.db

# View recent runs
SELECT run_id, run_timestamp, total_clusters, processed_clusters, status
FROM runs
ORDER BY run_id DESC
LIMIT 5;

# Exit
.exit
```

---

## Manual Execution

### Test with Small Number of Clusters

```bash
cd /opt/active-active-cost-analysis
sudo ./run_aa_report_with_creds.sh --limit 5
```

### Full Execution

```bash
cd /opt/active-active-cost-analysis
sudo ./run_aa_report_with_creds.sh
```

### Debug Mode

```bash
cd /opt/active-active-cost-analysis
sudo ./run_aa_report_with_creds.sh --log-level DEBUG --limit 1
```

### Without GCS Upload

```bash
cd /opt/active-active-cost-analysis
ENABLE_GCS_UPLOAD=false sudo ./run_aa_report_with_creds.sh --limit 5
```

---

## Troubleshooting

### Problem: "Permission denied" on Execution

```bash
# Solution: Make wrapper executable
sudo chmod +x /opt/active-active-cost-analysis/run_aa_report_with_creds.sh
```

### Problem: "Virtual environment not found"

```bash
# Check if venv exists
ls -la /var/vault-users-python3.11-env/

# Check if rcp_client is installed
ls -la /var/vault-users-python3.11-env/lib/python3.11/site-packages/ | grep rcp
```

### Problem: "RCP_PASSWORD not set"

```bash
# Edit wrapper and set password
sudo nano /opt/active-active-cost-analysis/run_aa_report_with_creds.sh
# Find: export RCP_PASSWORD="YOUR_PASSWORD_HERE"
# Change to: export RCP_PASSWORD="actual_password"
```

### Problem: GCS Upload Fails

```bash
# Test gsutil manually
gsutil ls gs://active-active-cost-analysis/

# Check user credentials
gcloud auth list

# Re-authenticate if needed
gcloud auth login
```

### Problem: Database Locked

```bash
# Check if another instance is running
ps aux | grep aa_report_automation

# Kill if needed
sudo pkill -f aa_report_automation.py

# Check database connections
lsof /opt/active-active-cost-analysis/aa_report_cache.db
```

---

## Update Process

### Updating Code

```bash
# 1. Backup current version
sudo cp /opt/active-active-cost-analysis/aa_report_automation.py \
       /opt/active-active-cost-analysis/aa_report_automation.py.backup

# 2. Copy new version
sudo cp ~/new_version/aa_report_automation.py /opt/active-active-cost-analysis/

# 3. Test
cd /opt/active-active-cost-analysis
sudo ./run_aa_report_with_creds.sh --limit 1

# 4. If there's a problem, restore backup
sudo cp /opt/active-active-cost-analysis/aa_report_automation.py.backup \
       /opt/active-active-cost-analysis/aa_report_automation.py
```

### Updating Credentials

```bash
# Edit wrapper
sudo nano /opt/active-active-cost-analysis/run_aa_report_with_creds.sh

# Change RCP_PASSWORD
# Save and exit
```

---

## Quick Reference

### Important Paths

```bash
# Application directory
/opt/active-active-cost-analysis/

# Virtual environment
/var/vault-users-python3.11-env/

# Database
/opt/active-active-cost-analysis/aa_report_cache.db

# Logs
/opt/active-active-cost-analysis/logs/

# GCS bucket
gs://active-active-cost-analysis/
```

### Important Commands

```bash
# Manual execution (test)
sudo ./run_aa_report_with_creds.sh --limit 5

# Manual execution (full)
sudo ./run_aa_report_with_creds.sh

# View cron jobs
sudo crontab -l

# View logs
tail -f logs/aa_report_automation_*.log

# Check GCS
gsutil ls -l gs://active-active-cost-analysis/

# Check database
sqlite3 aa_report_cache.db "SELECT COUNT(*) FROM runs;"
```

---

## New Setup Checklist

- [ ] Created directory `/opt/active-active-cost-analysis/`
- [ ] Copied all files
- [ ] Configured `run_aa_report_with_creds.sh` with RCP_PASSWORD
- [ ] Wrapper is `chmod 700`
- [ ] Tested with `--limit 1`
- [ ] Database created successfully
- [ ] GCS upload works
- [ ] Cron job added
- [ ] Logs are written correctly

---

**Last Updated:** 2025-11-14
**Version:** 1.0

