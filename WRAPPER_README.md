# Wrapper Scripts - Why and How

## 🤔 Why Use Wrapper Scripts?

### Problem: Virtual Environment Conflicts

The `rcp_client` library is installed in a virtual environment:
```
/var/vault-users-python3.11-env/
```

If you run `source /var/vault-users-python3.11-env/bin/activate` in your shell (especially as root):

❌ **Problems:**
- Changes global PATH for all subsequent commands
- Affects other scripts running in the same shell
- Can break system tools that rely on system Python
- Hard to debug when you forget you're in a venv
- Risky in cron jobs (venv persists across commands)

### Solution: Wrapper Scripts

✅ **Benefits:**
- Activates venv **only** for the AA report script
- Isolated execution (doesn't affect shell environment)
- Safe for cron jobs
- Predictable behavior
- Easy to manage credentials

---

## 📦 Available Wrapper Scripts

### 1. `run_aa_report_with_creds.sh` (Recommended for Production)

**Use when:** You want credentials embedded in the script

**Setup:**
```bash
# 1. Copy to /opt
sudo cp run_aa_report_with_creds.sh /opt/active-active-cost-analysis/

# 2. Edit and set password
sudo nano /opt/active-active-cost-analysis/run_aa_report_with_creds.sh
# Find: export RCP_PASSWORD="YOUR_PASSWORD_HERE"
# Change to: export RCP_PASSWORD="actual_password"

# 3. Protect the script
sudo chmod 700 /opt/active-active-cost-analysis/run_aa_report_with_creds.sh
sudo chown root:root /opt/active-active-cost-analysis/run_aa_report_with_creds.sh
```

**Usage:**
```bash
cd /opt/active-active-cost-analysis
sudo ./run_aa_report_with_creds.sh --limit 5
```

**Pros:**
- ✅ Self-contained (no external .env file needed)
- ✅ Easy to use
- ✅ Perfect for cron jobs

**Cons:**
- ⚠️ Credentials in script (must protect with chmod 700)

---

### 2. `run_aa_report.sh` (For .env file users)

**Use when:** You prefer credentials in a separate .env file

**Setup:**
```bash
# 1. Copy to /opt
sudo cp run_aa_report.sh /opt/active-active-cost-analysis/

# 2. Create .env file
sudo nano /opt/active-active-cost-analysis/.env
# Add:
# RCP_PASSWORD=your_password

# 3. Protect .env
sudo chmod 640 /opt/active-active-cost-analysis/.env
sudo chown root:ops /opt/active-active-cost-analysis/.env

# 4. Make wrapper executable
sudo chmod 755 /opt/active-active-cost-analysis/run_aa_report.sh
```

**Usage:**
```bash
cd /opt/active-active-cost-analysis
sudo ./run_aa_report.sh --limit 5
```

**Pros:**
- ✅ Credentials separate from code
- ✅ Can share wrapper script without exposing credentials

**Cons:**
- ⚠️ Requires .env file with correct permissions

---

## 🔒 Security Comparison

### Option A: Wrapper with embedded credentials
```bash
# File: run_aa_report_with_creds.sh
# Permissions: 700 (rwx------)
# Owner: root:root
# Security: Good (only root can read)
```

### Option B: Wrapper + .env file
```bash
# File: run_aa_report.sh
# Permissions: 755 (rwxr-xr-x)
# Owner: root:root

# File: .env
# Permissions: 640 (rw-r-----)
# Owner: root:ops
# Security: Good (root + ops group can read)
```

### Option C: Direct Python (NOT RECOMMENDED)
```bash
# Must activate venv in shell
source /var/vault-users-python3.11-env/bin/activate
# ❌ Affects entire shell session
# ❌ Risky for root
# ❌ Hard to use in cron
```

---

## 🚀 How Wrapper Scripts Work

```bash
#!/bin/bash
# 1. Set environment variables
export RCP_PASSWORD="password"

# 2. Run in subshell (isolated)
(
    # 3. Activate venv (only in subshell)
    source /var/vault-users-python3.11-env/bin/activate
    
    # 4. Run script
    cd /opt/active-active-cost-analysis
    python3 aa_report_automation.py "$@"
)
# 5. Subshell exits, venv deactivated automatically
# 6. Parent shell is unaffected
```

**Key:** The `( ... )` creates a **subshell** that:
- Inherits environment variables
- Can activate venv without affecting parent
- Exits cleanly when done
- Doesn't pollute parent shell

---

## 📋 Cron Job Examples

### Using wrapper with credentials (Recommended)
```bash
crontab -e

# Daily at 2 AM
0 2 * * * /opt/active-active-cost-analysis/run_aa_report_with_creds.sh >> /opt/active-active-cost-analysis/logs/cron.log 2>&1
```

### Using wrapper with .env
```bash
crontab -e

# Daily at 2 AM
0 2 * * * /opt/active-active-cost-analysis/run_aa_report.sh >> /opt/active-active-cost-analysis/logs/cron.log 2>&1
```

### Direct Python (Not recommended)
```bash
crontab -e

# Daily at 2 AM - COMPLEX AND RISKY
0 2 * * * source /var/vault-users-python3.11-env/bin/activate && cd /opt/active-active-cost-analysis && RCP_PASSWORD='pass' python3 aa_report_automation.py >> logs/cron.log 2>&1
```

---

## ✅ Recommendation

**Use `run_aa_report_with_creds.sh`** because:
1. ✅ Simplest setup
2. ✅ Most reliable for cron
3. ✅ Self-contained
4. ✅ Easy to troubleshoot
5. ✅ No .env permission issues

Just remember to:
- `chmod 700` to protect credentials
- `chown root:root` for extra security
- Keep backups of the script

---

## 🧪 Testing

```bash
# Test wrapper
cd /opt/active-active-cost-analysis
sudo ./run_aa_report_with_creds.sh --limit 1

# Check logs
tail -f logs/aa_report_automation_*.log

# Verify GCS upload
gsutil ls gs://active-active-cost-analysis/
```

---

## 🆘 Troubleshooting

### "Permission denied" when running wrapper
```bash
sudo chmod +x /opt/active-active-cost-analysis/run_aa_report_with_creds.sh
```

### "Virtual environment not found"
```bash
# Check if venv exists
ls -la /var/vault-users-python3.11-env/

# Update VENV_PATH in wrapper script if needed
```

### "RCP_PASSWORD not set"
```bash
# Edit wrapper and set password
sudo nano /opt/active-active-cost-analysis/run_aa_report_with_creds.sh
```

### Script runs but no output
```bash
# Check logs
tail -100 /opt/active-active-cost-analysis/logs/aa_report_automation_*.log
```

