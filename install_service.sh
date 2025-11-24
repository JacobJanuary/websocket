#!/bin/bash

# Signal WebSocket Server Service Installation Script
# This script installs and configures the systemd service

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_info() {
    echo -e "${GREEN}[i]${NC} $1"
}

echo "====================================="
echo "Signal WebSocket Service Installer"
echo "====================================="
echo ""

# Check if running with sudo
if [[ $EUID -ne 0 ]]; then
   print_error "This script must be run with sudo"
   echo "Usage: sudo ./install_service.sh"
   exit 1
fi

# Get the actual user (not root)
ACTUAL_USER="${SUDO_USER:-$USER}"
SERVICE_NAME="signal-websocket"
WORKING_DIR="$(pwd)"

print_info "Installing service for user: $ACTUAL_USER"
print_info "Working directory: $WORKING_DIR"

# Step 1: Create logs directory
echo ""
echo "Step 1: Creating logs directory..."
sudo -u $ACTUAL_USER mkdir -p "$WORKING_DIR/logs"
print_status "Logs directory created"

# Step 2: Kill any existing WebSocket server process
echo ""
echo "Step 2: Checking for existing processes..."
if pgrep -f "signal_websocket_server.py" > /dev/null; then
    print_warning "Found existing WebSocket server process"
    pkill -f "signal_websocket_server.py" || true
    sleep 2
    print_status "Stopped existing process"
else
    print_status "No existing process found"
fi

# Step 3: Update service file with correct user and paths
echo ""
echo "Step 3: Configuring service file..."
sed -i "s/User=elcrypto/User=$ACTUAL_USER/g" signal-websocket.service
sed -i "s/Group=elcrypto/Group=$ACTUAL_USER/g" signal-websocket.service
sed -i "s|WorkingDirectory=/home/elcrypto/websocket|WorkingDirectory=$WORKING_DIR|g" signal-websocket.service
sed -i "s|/home/elcrypto/websocket|$WORKING_DIR|g" signal-websocket.service
print_status "Service file configured"

# Step 4: Copy service file to systemd
echo ""
echo "Step 4: Installing systemd service..."
cp signal-websocket.service /etc/systemd/system/
print_status "Service file copied to /etc/systemd/system/"

# Step 5: Set correct permissions
chmod 644 /etc/systemd/system/signal-websocket.service
print_status "Service file permissions set"

# Step 6: Reload systemd
echo ""
echo "Step 5: Reloading systemd daemon..."
systemctl daemon-reload
print_status "Systemd daemon reloaded"

# Step 7: Enable service
echo ""
echo "Step 6: Enabling service for automatic startup..."
systemctl enable $SERVICE_NAME
print_status "Service enabled for automatic startup"

# Step 8: Start service
echo ""
echo "Step 7: Starting the service..."
systemctl start $SERVICE_NAME
sleep 2

# Step 9: Check service status
echo ""
echo "Step 8: Checking service status..."
if systemctl is-active --quiet $SERVICE_NAME; then
    print_status "Service is running successfully!"
    echo ""
    systemctl status $SERVICE_NAME --no-pager | head -n 10
else
    print_error "Service failed to start"
    echo ""
    echo "Recent logs:"
    journalctl -u $SERVICE_NAME -n 20 --no-pager
    exit 1
fi

# Print management commands
echo ""
echo "====================================="
print_status "Installation Complete!"
echo "====================================="
echo ""
echo "Service Management Commands:"
echo "  Start:    sudo systemctl start $SERVICE_NAME"
echo "  Stop:     sudo systemctl stop $SERVICE_NAME"
echo "  Restart:  sudo systemctl restart $SERVICE_NAME"
echo "  Status:   sudo systemctl status $SERVICE_NAME"
echo "  Enable:   sudo systemctl enable $SERVICE_NAME"
echo "  Disable:  sudo systemctl disable $SERVICE_NAME"
echo ""
echo "View Logs:"
echo "  Service logs:  sudo journalctl -u $SERVICE_NAME -f"
echo "  Application:   tail -f $WORKING_DIR/logs/server.log"
echo "  Errors:        tail -f $WORKING_DIR/logs/error.log"
echo ""
echo "The service will automatically start on system boot."
echo ""

# Test WebSocket connection
echo "Testing WebSocket connection..."
sleep 3

# Simple Python test
python3 << EOF
import asyncio
import websockets
import json

async def test():
    try:
        async with websockets.connect("ws://localhost:8765") as ws:
            msg = await ws.recv()
            print("  WebSocket server is responding: ✓")
            return True
    except Exception as e:
        print(f"  WebSocket test failed: {e}")
        return False

result = asyncio.run(test())
exit(0 if result else 1)
EOF

if [ $? -eq 0 ]; then
    print_status "WebSocket server is accessible on port 8765"
else
    print_warning "WebSocket test failed, but service is running"
    print_info "Check logs for details: sudo journalctl -u $SERVICE_NAME -n 50"
fi

echo ""
print_status "Service '$SERVICE_NAME' is now active and will auto-start on boot!"