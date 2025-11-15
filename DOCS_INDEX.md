# Documentation Index

## Where to Find What

### For Production Server (ip-10-0-0-88)

| Document | When to Use |
|----------|-------------|
| **[QUICKSTART.md](QUICKSTART.md)** | Quick reference - frequently used commands |
| **[SERVER_SETUP.md](SERVER_SETUP.md)** | Complete setup and maintenance documentation |
| **[WRAPPER_README.md](WRAPPER_README.md)** | Why wrapper scripts? How do they work? |

---

### For Development

| Document | When to Use |
|----------|-------------|
| **[README.md](README.md)** | Project overview |
| **[SETUP.md](SETUP.md)** | General setup instructions |
| **[CHANGELOG.md](CHANGELOG.md)** | What has changed |
| **[DEPLOYMENT.md](DEPLOYMENT.md)** | Cloud Run deployment guide |
| **[ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md)** | Environment variables reference |
| **[RCP.md](RCP.md)** | RCP automation tool documentation |

---

## Frequently Used Commands

### Manual Execution
```bash
cd /opt/active-active-cost-analysis
sudo ./run_aa_report_with_creds.sh --limit 5
```

### Check Logs
```bash
tail -f /opt/active-active-cost-analysis/logs/aa_report_automation_*.log
```

### Check Cron
```bash
sudo crontab -l
```

### Check GCS
```bash
gsutil ls -l gs://active-active-cost-analysis/
```

---

## File Structure

```
/opt/active-active-cost-analysis/
├── aa_report_automation.py         # Main script
├── aa_database.py                  # Database layer
├── run_aa_report_with_creds.sh     # Wrapper (chmod 700)
├── aa_report_cache.db              # SQLite database
└── logs/                           # Logs
    ├── aa_report_automation_*.log
    └── cron.log
```

---

## Troubleshooting

| Problem | Solution | Document |
|---------|----------|----------|
| Permission denied | `chmod +x run_aa_report_with_creds.sh` | [SERVER_SETUP.md](SERVER_SETUP.md#troubleshooting) |
| GCS upload fails | Check `gcloud auth list` | [SERVER_SETUP.md](SERVER_SETUP.md#problem-gcs-upload-fails) |
| Database locked | `pkill -f aa_report_automation.py` | [SERVER_SETUP.md](SERVER_SETUP.md#problem-database-locked) |
| Forgotten password | `nano run_aa_report_with_creds.sh` | [QUICKSTART.md](QUICKSTART.md#change-password) |

---

## Quick Reference

### Important Paths
- **App:** `/opt/active-active-cost-analysis/`
- **Venv:** `/var/vault-users-python3.11-env/`
- **GCS:** `gs://active-active-cost-analysis/`

### Important Files
- **Wrapper:** `run_aa_report_with_creds.sh` (contains credentials)
- **Database:** `aa_report_cache.db`
- **Logs:** `logs/aa_report_automation_*.log`

### Cron Schedule
```bash
# 7:00 UTC daily
0 7 * * * /opt/active-active-cost-analysis/run_aa_report_with_creds.sh >> /opt/active-active-cost-analysis/logs/cron.log 2>&1
```

---

**Last Updated:** 2025-11-14

