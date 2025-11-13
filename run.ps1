#!/usr/bin/env pwsh
# Quick start script for local development

Write-Host "================================" -ForegroundColor Cyan
Write-Host "Active-Active Cost Analysis" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""

# Check if database exists
if (-not (Test-Path "aa_report_cache.db")) {
    Write-Host "Error: Database file 'aa_report_cache.db' not found!" -ForegroundColor Red
    Write-Host "Please ensure the database file is in the project root." -ForegroundColor Yellow
    exit 1
}

# Check if Python is installed
$pythonVersion = python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: Python not found!" -ForegroundColor Red
    Write-Host "Please install Python 3.12+ from https://www.python.org/" -ForegroundColor Yellow
    exit 1
}
Write-Host "Python: $pythonVersion" -ForegroundColor Green

# Check if dependencies are installed
Write-Host "Checking dependencies..." -ForegroundColor Yellow
python -c "import flask" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing dependencies..." -ForegroundColor Yellow
    pip install -r requirements.txt
} else {
    Write-Host "Dependencies installed" -ForegroundColor Green
}

Write-Host ""
Write-Host "Starting Flask server..." -ForegroundColor Green
Write-Host "Access at: http://localhost:5000" -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host ""

# Run the application
python app.py

