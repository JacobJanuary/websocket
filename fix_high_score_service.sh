#!/bin/bash

# Quick Fix Script for High-Score Signal Service
# Fixes the EnvironmentFile issue and restarts the service

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_status() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

print_info() {
    echo -e "${GREEN}[i]${NC} $1"
}

echo "=========================================="
echo "High-Score Signal Service - Quick Fix"
echo "=========================================="
echo ""

# Check if running with sudo
if [[ $EUID -ne 0 ]]; then
   print_error "This script must be run with sudo"
   echo "Usage: sudo ./fix_high_score_service.sh"
   exit 1
fi

WORKING_DIR="$(pwd)"
SERVICE_NAME="high-score-signal-websocket"

print_info "Working directory: $WORKING_DIR"

# Step 1: Stop the service
echo ""
echo "Step 1: Stopping the service..."
systemctl stop $SERVICE_NAME 2>/dev/null || true
print_status "Service stopped"

# Step 2: Copy updated service file
echo ""
echo "Step 2: Updating service file..."
cp high-score-signal-websocket.service /etc/systemd/system/
chmod 644 /etc/systemd/system/high-score-signal-websocket.service
print_status "Service file updated"

# Step 3: Reload systemd
echo ""
echo "Step 3: Reloading systemd..."
systemctl daemon-reload
print_status "Systemd reloaded"

# Step 4: Start the service
echo ""
echo "Step 4: Starting the service..."
systemctl start $SERVICE_NAME
sleep 2

# Step 5: Check status
echo ""
echo "Step 5: Checking service status..."
if systemctl is-active --quiet $SERVICE_NAME; then
    print_status "Service is running!"
    echo ""
    systemctl status $SERVICE_NAME --no-pager | head -n 10
else
    print_error "Service failed to start"
    echo ""
    echo "Check error logs:"
    echo "  sudo journalctl -u $SERVICE_NAME -n 50"
    echo "  tail -n 50 $WORKING_DIR/logs/high_score_error.log"
    exit 1
fi

echo ""
echo "=========================================="
print_status "Service Fixed and Running!"
echo "=========================================="
