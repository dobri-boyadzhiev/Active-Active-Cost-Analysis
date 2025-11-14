# Setup Instructions for /opt/active-active-cost-analysis

## Quick Setup (Recommended - Using Wrapper Script)

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
sudo cp run_aa_report_with_creds.sh /opt/active-active-cost-analysis/
```

### 3. Edit wrapper script with credentials
```bash
# Edit the wrapper script
sudo nano /opt/active-active-cost-analysis/run_aa_report_with_creds.sh

# Set RCP_PASSWORD (around line 20):
# export RCP_PASSWORD="your_actual_password"

# Protect the script
sudo chmod 700 /opt/active-active-cost-analysis/run_aa_report_with_creds.sh
```

### 4. Test
```bash
cd /opt/active-active-cost-analysis
sudo ./run_aa_report_with_creds.sh --limit 5
```

---

## Alternative Setup (Using .env file)

### 1-2. Same as above

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
sudo chmod 640 /opt/active-active-cost-analysis/.env
sudo chown root:ops /opt/active-active-cost-analysis/.env
```

### 4. Copy wrapper script (without credentials)
```bash
sudo cp run_aa_report.sh /opt/active-active-cost-analysis/
sudo chmod 755 /opt/active-active-cost-analysis/run_aa_report.sh
```

### 5. Test
```bash
cd /opt/active-active-cost-analysis
sudo ./run_aa_report.sh --limit 5
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

### Using Wrapper Script (Recommended)

```bash
# Test with 5 clusters
cd /opt/active-active-cost-analysis
sudo ./run_aa_report_with_creds.sh --limit 5

# Full run
sudo ./run_aa_report_with_creds.sh

# With custom log level
sudo ./run_aa_report_with_creds.sh --log-level DEBUG
```

### Direct Python (if you prefer)

```bash
# Activate venv first
source /var/vault-users-python3.11-env/bin/activate

# Set credentials
export RCP_PASSWORD='your_password'

# Run
cd /opt/active-active-cost-analysis
python3 aa_report_automation.py --limit 5
```

## Cron Setup

### Using Wrapper Script (Recommended)

```bash
# Edit crontab (as your user or root)
crontab -e

# Add daily run at 2:00 AM
0 2 * * * /opt/active-active-cost-analysis/run_aa_report_with_creds.sh >> /opt/active-active-cost-analysis/logs/cron.log 2>&1
```

### Direct Python (alternative)

```bash
# Edit root crontab
sudo crontab -e

# Add daily run at 2:00 AM
0 2 * * * source /var/vault-users-python3.11-env/bin/activate && cd /opt/active-active-cost-analysis && RCP_PASSWORD='password' python3 aa_report_automation.py >> logs/cron.log 2>&1
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

