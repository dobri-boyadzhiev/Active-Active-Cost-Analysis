# Setup Instructions for /opt/active-active-cost-analysis

## Quick Setup

### 1. Create directory structure
```bash
sudo mkdir -p /opt/active-active-cost-analysis/logs
```

### 2. Copy files
```bash
# Copy all files to /opt
sudo cp aa_report_automation.py /opt/active-active-cost-analysis/
sudo cp aa_database.py /opt/active-active-cost-analysis/
sudo cp requirements.txt /opt/active-active-cost-analysis/
```

### 3. Create .env file
```bash
sudo cat > /opt/active-active-cost-analysis/.env << 'EOF'
RCP_SERVER=rcp-server-prod.redislabs.com
RCP_USERNAME=operations
RCP_PASSWORD=your_password_here
GCS_BUCKET_NAME=active-active-cost-analysis
ENABLE_GCS_UPLOAD=true
EOF

# Protect credentials
sudo chmod 600 /opt/active-active-cost-analysis/.env
```

### 4. Install dependencies (optional)
```bash
cd /opt/active-active-cost-analysis
sudo pip3 install -r requirements.txt
```

### 5. Test
```bash
cd /opt/active-active-cost-analysis
sudo python3 aa_report_automation.py --limit 5
```

## File Structure

```
/opt/active-active-cost-analysis/
├── aa_report_automation.py    # Main script
├── aa_database.py              # Database layer
├── requirements.txt            # Dependencies
├── .env                        # Credentials (chmod 600)
├── aa_report_cache.db          # Database (auto-created)
└── logs/                       # Logs directory
    └── aa_report_automation_YYYY-MM-DD.log
```

## Configuration

All configuration is done via `.env` file or environment variables:

- `RCP_SERVER` - RCP hostname (default: rcp-server-prod.redislabs.com)
- `RCP_USERNAME` - RCP username (default: operations)
- `RCP_PASSWORD` - RCP password (REQUIRED)
- `GCS_BUCKET_NAME` - GCS bucket name (default: active-active-cost-analysis)
- `ENABLE_GCS_UPLOAD` - Enable GCS upload (default: true)
- `DB_PATH` - Database path (default: script_dir/aa_report_cache.db)

## Usage

```bash
# Test with 5 clusters
cd /opt/active-active-cost-analysis
sudo python3 aa_report_automation.py --limit 5

# Full run
sudo python3 aa_report_automation.py

# With custom log level
sudo python3 aa_report_automation.py --log-level DEBUG
```

## Cron Setup

```bash
# Edit root crontab
sudo crontab -e

# Add daily run at 2:00 AM
0 2 * * * cd /opt/active-active-cost-analysis && python3 aa_report_automation.py >> logs/cron.log 2>&1
```

## GCS Upload

The script uses `gsutil` to upload the database to GCS. Make sure:

1. `gsutil` is installed and configured
2. You have permissions to write to the bucket
3. Service account has `storage.objectAdmin` role on the bucket

The script automatically:
- Temporarily removes `GOOGLE_APPLICATION_CREDENTIALS` env var
- Uses user credentials (from `gcloud auth`)
- Uploads database to `gs://active-active-cost-analysis/aa_report_cache.db`
- Restores service account credentials

## Troubleshooting

### Database locked error
If you see "database is locked", make sure no other instance is running.

### GCS upload fails
```bash
# Test gsutil manually
gsutil ls gs://active-active-cost-analysis/

# If fails, check credentials
gcloud auth list
```

### Permission denied
Make sure to run as root or with appropriate permissions:
```bash
sudo python3 aa_report_automation.py
```

