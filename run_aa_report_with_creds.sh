#!/bin/bash
#
# Active-Active Cost Analysis Report - Wrapper Script (with credentials)
# =======================================================================
#
# This version includes credentials directly in the script.
# Make sure to chmod 700 this file to protect credentials!
#
# Usage:
#   chmod 700 run_aa_report_with_creds.sh
#   ./run_aa_report_with_creds.sh [--limit N] [--log-level LEVEL]
#

set -e  # Exit on error

# Configuration
VENV_PATH="/var/vault-users-python3.11-env"
SCRIPT_DIR="/opt/active-active-cost-analysis"
SCRIPT_NAME="aa_report_automation.py"

# ============================================================================
# CREDENTIALS - SET THESE VALUES
# ============================================================================
export RCP_SERVER="rcp-server-prod.redislabs.com"
export RCP_USERNAME="operations"
export RCP_PASSWORD="YOUR_PASSWORD_HERE"  # ⚠️ SET THIS!

# GCS Configuration
export GCS_BUCKET_NAME="active-active-cost-analysis"
export ENABLE_GCS_UPLOAD="true"
# ============================================================================

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if password is set
if [ "$RCP_PASSWORD" = "YOUR_PASSWORD_HERE" ]; then
    echo -e "${RED}❌ Please set RCP_PASSWORD in this script${NC}"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "$VENV_PATH" ]; then
    echo -e "${RED}❌ Virtual environment not found: $VENV_PATH${NC}"
    exit 1
fi

# Check if script exists
if [ ! -f "$SCRIPT_DIR/$SCRIPT_NAME" ]; then
    echo -e "${RED}❌ Script not found: $SCRIPT_DIR/$SCRIPT_NAME${NC}"
    exit 1
fi

# Print configuration (without password)
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}AA Report Automation - Starting${NC}"
echo -e "${GREEN}========================================${NC}"
echo "Virtual Env: $VENV_PATH"
echo "Script Dir:  $SCRIPT_DIR"
echo "RCP Server:  $RCP_SERVER"
echo "RCP User:    $RCP_USERNAME"
echo "GCS Bucket:  $GCS_BUCKET_NAME"
echo "GCS Upload:  $ENABLE_GCS_UPLOAD"
echo "Arguments:   $@"
echo -e "${GREEN}========================================${NC}"
echo ""

# Activate virtual environment and run script in subshell
(
    source "$VENV_PATH/bin/activate"
    cd "$SCRIPT_DIR"
    python3 "$SCRIPT_NAME" "$@"
)

# Capture exit code
EXIT_CODE=$?

echo ""
echo -e "${GREEN}========================================${NC}"
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✅ Script completed successfully${NC}"
    echo -e "${GREEN}Database: $SCRIPT_DIR/aa_report_cache.db${NC}"
    echo -e "${GREEN}Logs: $SCRIPT_DIR/logs/${NC}"
    if [ "$ENABLE_GCS_UPLOAD" = "true" ]; then
        echo -e "${GREEN}GCS: gs://$GCS_BUCKET_NAME/aa_report_cache.db${NC}"
    fi
else
    echo -e "${RED}❌ Script failed with exit code: $EXIT_CODE${NC}"
fi
echo -e "${GREEN}========================================${NC}"

exit $EXIT_CODE

