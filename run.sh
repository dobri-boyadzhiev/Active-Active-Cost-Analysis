#!/bin/bash
# Quick start script for local development

echo "================================"
echo "Active-Active Cost Analysis"
echo "================================"
echo ""

# Check if database exists
if [ ! -f "aa_report_cache.db" ]; then
    echo "[ERROR] Database file 'aa_report_cache.db' not found!"
    echo "        Please ensure the database file is in the project root."
    exit 1
fi

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python not found!"
    echo "        Please install Python 3.12+ from https://www.python.org/"
    exit 1
fi

PYTHON_VERSION=$(python3 --version)
echo "[OK] Python: $PYTHON_VERSION"

# Check if dependencies are installed
echo "[INFO] Checking dependencies..."
if ! python3 -c "import flask" 2>/dev/null; then
    echo "[INFO] Installing dependencies..."
    pip3 install -r requirements.txt
else
    echo "[OK] Dependencies installed"
fi

echo ""
echo "[INFO] Starting Flask server..."
echo "       Access at: http://localhost:5000"
echo "       Press Ctrl+C to stop"
echo ""

# Run the application
python3 app.py

