# Changes Summary

## ✅ Направени промени

### 1. **Всичко на едно място в script директорията**
- ✅ Database: `script_dir/aa_report_cache.db` (вместо `~/aa_report_cache.db`)
- ✅ Logs: `script_dir/logs/` (вместо `~/logs/`)
- ✅ Config: `script_dir/.env` (нов файл)

### 2. **Добавена .env поддръжка**
- ✅ Автоматично зарежда `.env` файл от script директорията
- ✅ Fallback към environment variables ако няма `.env`
- ✅ Работи и без `python-dotenv` (опционално)

### 3. **GCS upload с gsutil вместо Python библиотека**
- ✅ Използва `gsutil cp` вместо `google-cloud-storage`
- ✅ Не изисква допълнителни Python библиотеки
- ✅ Временно премахва `GOOGLE_APPLICATION_CREDENTIALS` за да използва user credentials
- ✅ Автоматично връща обратно service account credentials след upload

### 4. **Опростени dependencies**
- ✅ Премахнат `google-cloud-storage` от requirements.txt
- ✅ Само `python-dotenv` (опционално)
- ✅ Всички останали са built-in Python модули

### 5. **Документация**
- ✅ Създаден `SETUP.md` с инструкции за setup
- ✅ Обновен `requirements.txt` с коментари
- ✅ `.env.example` template файл

## 📂 Файлова структура

```
/opt/active-active-cost-analysis/
├── aa_report_automation.py    # Main script (UPDATED)
├── aa_database.py              # Database layer (no changes)
├── requirements.txt            # Dependencies (UPDATED)
├── .env                        # Credentials (CREATE THIS)
├── .env.example                # Template
├── SETUP.md                    # Setup instructions (NEW)
├── CHANGES.md                  # This file (NEW)
├── aa_report_cache.db          # Database (auto-created)
└── logs/                       # Logs (auto-created)
    └── aa_report_automation_*.log
```

## 🚀 Следващи стъпки

1. **Копирай файловете в /opt:**
   ```bash
   sudo mkdir -p /opt/active-active-cost-analysis/logs
   sudo cp aa_report_automation.py aa_database.py requirements.txt /opt/active-active-cost-analysis/
   ```

2. **Създай .env файл:**
   ```bash
   sudo nano /opt/active-active-cost-analysis/.env
   # Добави credentials
   sudo chmod 600 /opt/active-active-cost-analysis/.env
   ```

3. **Инсталирай dependencies (опционално):**
   ```bash
   cd /opt/active-active-cost-analysis
   sudo pip3 install python-dotenv
   ```

4. **Тествай:**
   ```bash
   cd /opt/active-active-cost-analysis
   sudo python3 aa_report_automation.py --limit 5
   ```

## 🔍 Какво да провериш

- [ ] `gsutil ls gs://active-active-cost-analysis/` работи под root
- [ ] `.env` файл съществува и има правилни credentials
- [ ] Database се създава в `/opt/active-active-cost-analysis/aa_report_cache.db`
- [ ] Logs отиват в `/opt/active-active-cost-analysis/logs/`
- [ ] GCS upload работи (проверка в logs)

## ⚠️ Важно

- **Credentials security**: `.env` файлът трябва да е `chmod 600`
- **Run as root**: Скриптът трябва да се пуска като root (за gsutil достъп)
- **GCS permissions**: Service account `terraform-service@rcp-prod.iam.gserviceaccount.com` вече има `storage.objectAdmin` роля

