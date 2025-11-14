# Active-Active Cost Analysis - Server Setup Guide
# Пълна документация за настройка на сървъра

## 📋 Преглед

Този документ описва как да setup-неш и поддържаш AA Cost Analysis automation на production сървър.

**Сървър:** `ip-10-0-0-88`  
**Локация:** `/opt/active-active-cost-analysis/`  
**Virtual Environment:** `/var/vault-users-python3.11-env/`  
**GCS Bucket:** `gs://active-active-cost-analysis/`

---

## 🚀 Първоначална настройка (One-time setup)

### Стъпка 1: Създай директория

```bash
sudo mkdir -p /opt/active-active-cost-analysis/logs
```

### Стъпка 2: Копирай файловете

```bash
# От development директория
cd ~/path/to/project

# Копирай всички файлове
sudo cp aa_report_automation.py /opt/active-active-cost-analysis/
sudo cp aa_database.py /opt/active-active-cost-analysis/
sudo cp requirements.txt /opt/active-active-cost-analysis/
sudo cp run_aa_report_with_creds.sh /opt/active-active-cost-analysis/
```

### Стъпка 3: Настрой wrapper скрипта с credentials

```bash
# Редактирай wrapper скрипта
sudo nano /opt/active-active-cost-analysis/run_aa_report_with_creds.sh

# Намери този ред (около ред 20):
# export RCP_PASSWORD="YOUR_PASSWORD_HERE"

# Замени с реалната парола:
# export RCP_PASSWORD="actual_rcp_password"

# Запази и излез (Ctrl+O, Enter, Ctrl+X)
```

### Стъпка 4: Направи wrapper executable и защити го

```bash
# Направи executable
sudo chmod 700 /opt/active-active-cost-analysis/run_aa_report_with_creds.sh

# Провери permissions
ls -la /opt/active-active-cost-analysis/run_aa_report_with_creds.sh
# Трябва да видиш: -rwx------ 1 root root ... run_aa_report_with_creds.sh
```

### Стъпка 5: Тествай

```bash
# Тест с 1 cluster
cd /opt/active-active-cost-analysis
sudo ./run_aa_report_with_creds.sh --limit 1

# Провери logs
tail -f /opt/active-active-cost-analysis/logs/aa_report_automation_*.log

# Провери database
ls -lh /opt/active-active-cost-analysis/aa_report_cache.db

# Провери GCS upload
gsutil ls gs://active-active-cost-analysis/
```

---

## ⏰ Cron Job Setup

### Настройка на автоматично изпълнение

```bash
# Отвори crontab (като root)
sudo crontab -e

# Добави този ред за изпълнение всеки ден в 7:00 UTC:
0 7 * * * /opt/active-active-cost-analysis/run_aa_report_with_creds.sh >> /opt/active-active-cost-analysis/logs/cron.log 2>&1
```

### Други полезни времена

```bash
# Всеки ден в 2:00 UTC
0 2 * * * /opt/active-active-cost-analysis/run_aa_report_with_creds.sh >> /opt/active-active-cost-analysis/logs/cron.log 2>&1

# Всеки ден в 7:00 UTC
0 7 * * * /opt/active-active-cost-analysis/run_aa_report_with_creds.sh >> /opt/active-active-cost-analysis/logs/cron.log 2>&1

# Всеки понеделник в 7:00 UTC
0 7 * * 1 /opt/active-active-cost-analysis/run_aa_report_with_creds.sh >> /opt/active-active-cost-analysis/logs/cron.log 2>&1
```

### За Bulgaria time (EET/EEST)

```bash
# Добави в началото на crontab:
TZ=Europe/Sofia

# После добави job-а:
0 7 * * * /opt/active-active-cost-analysis/run_aa_report_with_creds.sh >> /opt/active-active-cost-analysis/logs/cron.log 2>&1
```

### Провери cron jobs

```bash
# Виж активните cron jobs
sudo crontab -l

# Провери cron logs
grep CRON /var/log/syslog | tail -20

# Провери application logs
tail -f /opt/active-active-cost-analysis/logs/cron.log
```

---

## 📂 Файлова структура

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

## 🔧 Конфигурация

### Wrapper Script Configuration

Всички настройки са в `run_aa_report_with_creds.sh`:

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

Скриптът използва shared virtual environment:
- **Path:** `/var/vault-users-python3.11-env/`
- **Owner:** `EranCahana:ops`
- **Съдържа:** `rcp_client`, `rcp_api_client`, `rcp_cli` и други RCP библиотеки

⚠️ **Важно:** Wrapper скриптът автоматично активира venv, не е нужно да го правиш ръчно!

---

## 🔐 Security & Permissions

### Препоръчителни permissions

```bash
# Wrapper script (съдържа credentials)
-rwx------ 1 root root  run_aa_report_with_creds.sh  # chmod 700

# Python scripts (без credentials)
-rw-r--r-- 1 root root  aa_report_automation.py      # chmod 644
-rw-r--r-- 1 root root  aa_database.py               # chmod 644

# Database (може да съдържа sensitive data)
-rw-r--r-- 1 root root  aa_report_cache.db           # chmod 644

# Logs directory
drwxr-xr-x 2 root root  logs/                        # chmod 755
```

### GCS Authentication

Скриптът използва **user credentials** (не service account):

1. Временно премахва `GOOGLE_APPLICATION_CREDENTIALS` env var
2. Използва credentials от `gcloud auth` (user credentials)
3. Upload-ва database с `gsutil cp`
4. Връща обратно `GOOGLE_APPLICATION_CREDENTIALS`

```bash
# Провери user credentials
gcloud auth list

# Провери GCS достъп
gsutil ls gs://active-active-cost-analysis/
```

---

## 📊 Мониторинг и Logs

### Log файлове

```bash
# Daily application logs
/opt/active-active-cost-analysis/logs/aa_report_automation_YYYY-MM-DD.log

# Cron execution logs
/opt/active-active-cost-analysis/logs/cron.log

# System cron logs
/var/log/syslog  # grep CRON
```

### Провери последно изпълнение

```bash
# Виж последните logs
tail -100 /opt/active-active-cost-analysis/logs/aa_report_automation_*.log

# Виж cron logs
tail -50 /opt/active-active-cost-analysis/logs/cron.log

# Провери database size
ls -lh /opt/active-active-cost-analysis/aa_report_cache.db

# Провери GCS upload timestamp
gsutil ls -l gs://active-active-cost-analysis/aa_report_cache.db
```

### Провери database съдържание

```bash
# Влез в database
sqlite3 /opt/active-active-cost-analysis/aa_report_cache.db

# Виж последните runs
SELECT run_id, run_timestamp, total_clusters, processed_clusters, status 
FROM runs 
ORDER BY run_id DESC 
LIMIT 5;

# Излез
.exit
```

---

## 🔄 Ръчно изпълнение

### Тест с малък брой clusters

```bash
cd /opt/active-active-cost-analysis
sudo ./run_aa_report_with_creds.sh --limit 5
```

### Пълно изпълнение

```bash
cd /opt/active-active-cost-analysis
sudo ./run_aa_report_with_creds.sh
```

### Debug mode

```bash
cd /opt/active-active-cost-analysis
sudo ./run_aa_report_with_creds.sh --log-level DEBUG --limit 1
```

### Без GCS upload

```bash
cd /opt/active-active-cost-analysis
ENABLE_GCS_UPLOAD=false sudo ./run_aa_report_with_creds.sh --limit 5
```

---

## 🆘 Troubleshooting

### Problem: "Permission denied" при изпълнение

```bash
# Solution: Направи wrapper executable
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

### Problem: GCS upload fails

```bash
# Test gsutil manually
gsutil ls gs://active-active-cost-analysis/

# Check user credentials
gcloud auth list

# Re-authenticate if needed
gcloud auth login
```

### Problem: Database locked

```bash
# Check if another instance is running
ps aux | grep aa_report_automation

# Kill if needed
sudo pkill -f aa_report_automation.py

# Check database connections
lsof /opt/active-active-cost-analysis/aa_report_cache.db
```

---

## 🔄 Update Process

### Обновяване на кода

```bash
# 1. Backup текущата версия
sudo cp /opt/active-active-cost-analysis/aa_report_automation.py \
       /opt/active-active-cost-analysis/aa_report_automation.py.backup

# 2. Копирай новата версия
sudo cp ~/new_version/aa_report_automation.py /opt/active-active-cost-analysis/

# 3. Тествай
cd /opt/active-active-cost-analysis
sudo ./run_aa_report_with_creds.sh --limit 1

# 4. Ако има проблем, върни backup-а
sudo cp /opt/active-active-cost-analysis/aa_report_automation.py.backup \
       /opt/active-active-cost-analysis/aa_report_automation.py
```

### Обновяване на credentials

```bash
# Редактирай wrapper
sudo nano /opt/active-active-cost-analysis/run_aa_report_with_creds.sh

# Промени RCP_PASSWORD
# Запази и излез
```

---

## 📞 Quick Reference

### Важни пътища

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

### Важни команди

```bash
# Ръчно изпълнение (test)
sudo ./run_aa_report_with_creds.sh --limit 5

# Ръчно изпълнение (full)
sudo ./run_aa_report_with_creds.sh

# Виж cron jobs
sudo crontab -l

# Виж logs
tail -f logs/aa_report_automation_*.log

# Провери GCS
gsutil ls -l gs://active-active-cost-analysis/

# Провери database
sqlite3 aa_report_cache.db "SELECT COUNT(*) FROM runs;"
```

---

## ✅ Checklist за нов setup

- [ ] Създадена директория `/opt/active-active-cost-analysis/`
- [ ] Копирани всички файлове
- [ ] Настроен `run_aa_report_with_creds.sh` с RCP_PASSWORD
- [ ] Wrapper е `chmod 700`
- [ ] Тестван с `--limit 1`
- [ ] Database се създава успешно
- [ ] GCS upload работи
- [ ] Cron job е добавен
- [ ] Logs се записват правилно

---

**Последна актуализация:** 2025-11-14  
**Версия:** 1.0

