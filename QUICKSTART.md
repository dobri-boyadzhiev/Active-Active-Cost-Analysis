# Quick Start Guide - Production Server

## 🚀 Quick Reference for Production Server

### Location
```
/opt/active-active-cost-analysis/
```

---

## ⚡ Manual Execution

```bash
# Test with 5 clusters
cd /opt/active-active-cost-analysis
sudo ./run_aa_report_with_creds.sh --limit 5

# Full execution
sudo ./run_aa_report_with_creds.sh

# Debug mode
sudo ./run_aa_report_with_creds.sh --log-level DEBUG --limit 1
```

---

## 📊 Check Results

```bash
# View logs
tail -f /opt/active-active-cost-analysis/logs/aa_report_automation_*.log

# View cron logs
tail -f /opt/active-active-cost-analysis/logs/cron.log

# Check database
ls -lh /opt/active-active-cost-analysis/aa_report_cache.db

# Check GCS upload
gsutil ls -l gs://active-active-cost-analysis/
```

---

## ⏰ Cron Job

```bash
# View cron jobs
sudo crontab -l

# Edit cron
sudo crontab -e

# Add for 7:00 UTC daily:
0 7 * * * /opt/active-active-cost-analysis/run_aa_report_with_creds.sh >> /opt/active-active-cost-analysis/logs/cron.log 2>&1
```

---

## 🔧 Change Password

```bash
# Edit wrapper
sudo nano /opt/active-active-cost-analysis/run_aa_report_with_creds.sh

# Find and change:
# export RCP_PASSWORD="your_password"

# Save: Ctrl+O, Enter, Ctrl+X
```

---

## 🆘 Troubleshooting

### Permission denied
```bash
sudo chmod +x /opt/active-active-cost-analysis/run_aa_report_with_creds.sh
```

### GCS upload fails
```bash
gsutil ls gs://active-active-cost-analysis/
gcloud auth list
```

### Database locked
```bash
ps aux | grep aa_report_automation
sudo pkill -f aa_report_automation.py
```

---

## 📚 Full Documentation

See **[SERVER_SETUP.md](SERVER_SETUP.md)** for complete instructions!

