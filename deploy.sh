#!/bin/bash

# ==============================================================================
# 🚀 AUTOMATED DEPLOYMENT SCRIPT FOR DJANGO (SCHMGMT)
# ==============================================================================
# This script automates pulling git updates, installing requirements, running
# migrations, collecting static files, and reloading the application server.
# ==============================================================================

# Exit immediately if a command exits with a non-zero status
set -e

# --- Colors for Output ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}====================================================${NC}"
echo -e "${BLUE}   🚀 Starting Deployment at $(date)   ${NC}"
echo -e "${BLUE}====================================================${NC}"

# --- Configuration ---
# Get the directory where the script is located
PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$PROJECT_DIR"

VENV_DIR="venv"
REQUIREMENTS_FILE="requirements.txt"
LOG_FILE="deployment.log"

# --- Logging Helper ---
log_message() {
    local type="$1"
    local msg="$2"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "[$timestamp] [$type] $msg" >> "$LOG_FILE"
}

# --- Step 1: Check Git Status & Pull Updates ---
echo -e "${YELLOW}[1/6] Fetching updates from Git...${NC}"
if [ -d ".git" ]; then
    # Check for local uncommitted changes
    if ! git diff-index --quiet HEAD --; then
        echo -e "${YELLOW}⚠️ Local changes detected. Stashing changes to prevent merge conflicts...${NC}"
        git stash
        log_message "INFO" "Local changes stashed automatically"
        STASHED=true
    else
        STASHED=false
    fi

    # Pull updates for the current active branch
    CURRENT_BRANCH=$(git branch --show-current)
    echo -e "${GREEN}Pulling latest changes for branch: $CURRENT_BRANCH...${NC}"
    git pull origin "$CURRENT_BRANCH"
    log_message "SUCCESS" "Pulled latest changes from branch $CURRENT_BRANCH"

    # Restore local changes if stashed
    if [ "$STASHED" = true ]; then
        echo -e "${GREEN}Restoring stashed local changes...${NC}"
        git stash pop || true
        log_message "INFO" "Stashed changes restored"
    fi
else
    echo -e "${RED}❌ Error: Not a git repository. Skipping git pull.${NC}"
    log_message "WARNING" "Not a git repository, skipping pull"
fi

# --- Step 2: Activate Virtual Environment ---
echo -e "${YELLOW}[2/6] Activating virtual environment...${NC}"
if [ -d "$VENV_DIR" ]; then
    source "$VENV_DIR/bin/activate"
    echo -e "${GREEN}✅ Virtual environment activated successfully.${NC}"
else
    echo -e "${RED}⚠️ Virtual environment '$VENV_DIR' not found in root. Trying default python3 commands...${NC}"
    log_message "WARNING" "Virtual environment not found, proceeding with global python"
fi

# --- Step 3: Install/Update Dependencies ---
echo -e "${YELLOW}[3/6] Installing dependencies...${NC}"
if [ -f "$REQUIREMENTS_FILE" ]; then
    pip install --upgrade pip
    pip install -r "$REQUIREMENTS_FILE"
    echo -e "${GREEN}✅ Dependencies installed/updated successfully.${NC}"
    log_message "SUCCESS" "Dependencies updated"
else
    echo -e "${YELLOW}⚠️ $REQUIREMENTS_FILE not found. Skipping pip install.${NC}"
fi

# --- Step 4: Run Migrations ---
echo -e "${YELLOW}[4/6] Running database migrations...${NC}"
python manage.py makemigrations --no-input || true
python manage.py migrate --no-input
echo -e "${GREEN}✅ Database migrations completed.${NC}"
log_message "SUCCESS" "Database migrations complete"

# --- Step 5: Collect Static Files ---
echo -e "${YELLOW}[5/6] Collecting static files...${NC}"
python manage.py collectstatic --no-input
echo -e "${GREEN}✅ Static files collected successfully.${NC}"
log_message "SUCCESS" "Static files collected"

# --- Step 6: Restart/Reload Server ---
echo -e "${YELLOW}[6/6] Reloading application server...${NC}"

# Detect reload mechanisms
RESTARTED=false

# 1. Phusion Passenger (Common on shared cPanel, A2 Hosting, Namecheap, PythonAnywhere, or VPS hosts)
if [ -d "tmp" ]; then
    touch tmp/restart.txt
    echo -e "${GREEN}✅ Touched tmp/restart.txt (Phusion Passenger reloaded).${NC}"
    log_message "SUCCESS" "Passenger server reloaded via tmp/restart.txt"
    RESTARTED=true
fi

# 2. Gunicorn / UWSGI Systemd Services (if sudo is configured or systemctl is accessible)
# Users can customize their service name here: e.g. "gunicorn" or "uwsgi" or "django"
SYSTEMD_SERVICE="gunicorn" 

if systemctl is-active --quiet "$SYSTEMD_SERVICE" 2>/dev/null; then
    echo -e "${GREEN}Found active systemd service: $SYSTEMD_SERVICE. Restarting...${NC}"
    sudo systemctl restart "$SYSTEMD_SERVICE" || true
    log_message "SUCCESS" "Systemd service $SYSTEMD_SERVICE restarted"
    RESTARTED=true
fi

# 3. Apache2 (common when Django is served behind mod_wsgi or reverse-proxied)
APACHE_SERVICE="apache2"

if systemctl is-active --quiet "$APACHE_SERVICE" 2>/dev/null; then
    echo -e "${GREEN}Found active systemd service: $APACHE_SERVICE. Restarting...${NC}"
    sudo systemctl restart "$APACHE_SERVICE" || true
    log_message "SUCCESS" "Systemd service $APACHE_SERVICE restarted"
    RESTARTED=true
fi

if [ "$RESTARTED" = false ]; then
    echo -e "${YELLOW}⚠️ No auto-detected server daemon (gunicorn/apache2/passenger) was restarted.${NC}"
    echo -e "${YELLOW}   If running Gunicorn, Apache2, or Uwsgi via systemctl, you may want to run:${NC}"
    echo -e "${BLUE}   sudo systemctl restart gunicorn${NC}"
    echo -e "${BLUE}   sudo systemctl restart apache2${NC}"
    log_message "INFO" "No standard reload mechanism triggered"
fi

echo -e "${BLUE}====================================================${NC}"
echo -e "${GREEN}🚀 DEPLOYMENT COMPLETED SUCCESSFULLY AT $(date) 🚀${NC}"
echo -e "${BLUE}====================================================${NC}"
log_message "DEPLOY" "Full deployment completed successfully"
