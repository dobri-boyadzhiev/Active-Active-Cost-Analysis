# Documentation Index

## 🎯 Къде да намериш какво

### За Production Server (ip-10-0-0-88)

| Документ | Кога да го използваш |
|----------|---------------------|
| **[QUICKSTART.md](QUICKSTART.md)** | 🔥 Бърза справка - често използвани команди |
| **[SERVER_SETUP.md](SERVER_SETUP.md)** | 📖 Пълна документация за setup и поддръжка |
| **[WRAPPER_README.md](WRAPPER_README.md)** | 🤔 Защо wrapper? Как работи? |

---

### За Development

| Документ | Кога да го използваш |
|----------|---------------------|
| **[README.md](README.md)** | 👋 Общ преглед на проекта |
| **[SETUP.md](SETUP.md)** | 🔧 Общи setup инструкции |
| **[CHANGES.md](CHANGES.md)** | 📝 Какво е променено |

---

## 🚀 Често използвани команди

### Ръчно изпълнение
```bash
cd /opt/active-active-cost-analysis
sudo ./run_aa_report_with_creds.sh --limit 5
```

### Провери logs
```bash
tail -f /opt/active-active-cost-analysis/logs/aa_report_automation_*.log
```

### Провери cron
```bash
sudo crontab -l
```

### Провери GCS
```bash
gsutil ls -l gs://active-active-cost-analysis/
```

---

## 📂 Файлова структура

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

## 🆘 Troubleshooting

| Проблем | Решение | Документ |
|---------|---------|----------|
| Permission denied | `chmod +x run_aa_report_with_creds.sh` | [SERVER_SETUP.md](SERVER_SETUP.md#troubleshooting) |
| GCS upload fails | Провери `gcloud auth list` | [SERVER_SETUP.md](SERVER_SETUP.md#problem-gcs-upload-fails) |
| Database locked | `pkill -f aa_report_automation.py` | [SERVER_SETUP.md](SERVER_SETUP.md#problem-database-locked) |
| Забравена парола | `nano run_aa_report_with_creds.sh` | [QUICKSTART.md](QUICKSTART.md#-промяна-на-парола) |

---

## 📞 Quick Reference

### Важни пътища
- **App:** `/opt/active-active-cost-analysis/`
- **Venv:** `/var/vault-users-python3.11-env/`
- **GCS:** `gs://active-active-cost-analysis/`

### Важни файлове
- **Wrapper:** `run_aa_report_with_creds.sh` (съдържа credentials)
- **Database:** `aa_report_cache.db`
- **Logs:** `logs/aa_report_automation_*.log`

### Cron времена
```bash
# 7:00 UTC всеки ден
0 7 * * * /opt/active-active-cost-analysis/run_aa_report_with_creds.sh >> /opt/active-active-cost-analysis/logs/cron.log 2>&1
```

---

**Последна актуализация:** 2025-11-14

