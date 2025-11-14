#!/bin/bash
#
# Active-Active Cost Analysis Report - Wrapper Script
# ====================================================
#
# This script activates the virtual environment and runs the AA report automation.
# It's safe to run from any user (including root) and won't affect the shell environment.
#
# Usage:
#   ./run_aa_report.sh [--limit N] [--log-level LEVEL]
#
# Examples:
#   ./run_aa_report.sh --limit 5          # Test with 5 clusters
#   ./run_aa_report.sh                    # Full run
#   ./run_aa_report.sh --log-level DEBUG  # Debug mode
#

set -e  # Exit on error

# Configuration
VENV_PATH="/var/vault-users-python3.11-env"
SCRIPT_DIR="/opt/active-active-cost-analysis"
SCRIPT_NAME="aa_report_automation.py"

# RCP Credentials (set these or use .env file)
export RCP_SERVER="${RCP_SERVER:-rcp-server-prod.redislabs.com}"
export RCP_USERNAME="${RCP_USERNAME:-operations}"
# export RCP_PASSWORD="your_password_here"  # Uncomment and set password

# GCS Configuration
export GCS_BUCKET_NAME="${GCS_BUCKET_NAME:-active-active-cost-analysis}"
export ENABLE_GCS_UPLOAD="${ENABLE_GCS_UPLOAD:-true}"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

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

# Check if RCP_PASSWORD is set
if [ -z "$RCP_PASSWORD" ]; then
    echo -e "${YELLOW}⚠️  RCP_PASSWORD not set. Checking .env file...${NC}"
    if [ -f "$SCRIPT_DIR/.env" ]; then
        echo -e "${GREEN}✅ .env file found, will be loaded by script${NC}"
    else
        echo -e "${RED}❌ RCP_PASSWORD not set and no .env file found${NC}"
        echo -e "${YELLOW}Please set RCP_PASSWORD environment variable or create .env file${NC}"
        exit 1
    fi
fi

# Print configuration
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

# Activate virtual environment and run script
# Note: We use a subshell to avoid affecting the current shell
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
else
    echo -e "${RED}❌ Script failed with exit code: $EXIT_CODE${NC}"
fi
echo -e "${GREEN}========================================${NC}"

exit $EXIT_CODE

