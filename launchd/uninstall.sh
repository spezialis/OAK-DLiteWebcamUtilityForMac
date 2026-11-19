#!/bin/bash
# Removes the OAK webcam LaunchAgent and its installed copy. Logs are kept.
set -euo pipefail

LABEL="ch.stellaspeziali.oakwebcam"
INSTALL_DIR="$HOME/Library/Application Support/OAKWebcam"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null && echo "==> Stopped service" || true
rm -f "$PLIST" && echo "==> Removed $PLIST"
rm -rf "$INSTALL_DIR" && echo "==> Removed $INSTALL_DIR"
echo "Logs kept in $HOME/Library/Logs/OAKWebcam"
