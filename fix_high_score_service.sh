#!/bin/bash
# Quick fix - applies the corrected service file

sudo systemctl stop high-score-signal-websocket 2>/dev/null || true
sudo cp high-score-signal-websocket.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start high-score-signal-websocket
sleep 2
sudo systemctl status high-score-signal-websocket
