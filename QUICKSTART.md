# Quick Start Guide - Production Server

## 🚀 За бърза справка на сървъра

### Локация
```
/opt/active-active-cost-analysis/
```

---

## ⚡ Ръчно изпълнение

```bash
# Тест с 5 clusters
cd /opt/active-active-cost-analysis
sudo ./run_aa_report_with_creds.sh --limit 5

# Пълно изпълнение
sudo ./run_aa_report_with_creds.sh

# Debug mode
sudo ./run_aa_report_with_creds.sh --log-level DEBUG --limit 1
```

---

## 📊 Провери резултати

```bash
# Виж logs
tail -f /opt/active-active-cost-analysis/logs/aa_report_automation_*.log

# Виж cron logs
tail -f /opt/active-active-cost-analysis/logs/cron.log

# Провери database
ls -lh /opt/active-active-cost-analysis/aa_report_cache.db

# Провери GCS upload
gsutil ls -l gs://active-active-cost-analysis/
```

---

## ⏰ Cron Job

```bash
# Виж cron jobs
sudo crontab -l

# Редактирай cron
sudo crontab -e

# Добави за 7:00 UTC всеки ден:
0 7 * * * /opt/active-active-cost-analysis/run_aa_report_with_creds.sh >> /opt/active-active-cost-analysis/logs/cron.log 2>&1
```

---

## 🔧 Промяна на парола

```bash
# Редактирай wrapper
sudo nano /opt/active-active-cost-analysis/run_aa_report_with_creds.sh

# Намери и промени:
# export RCP_PASSWORD="your_password"

# Запази: Ctrl+O, Enter, Ctrl+X
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

## 📚 Пълна документация

Виж **[SERVER_SETUP.md](SERVER_SETUP.md)** за пълни инструкции!

