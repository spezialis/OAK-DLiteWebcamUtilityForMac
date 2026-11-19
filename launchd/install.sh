#!/bin/bash
# Installs the OAK webcam background service as a per-user LaunchAgent.
#
# The service is copied to ~/Library/Application Support/OAKWebcam with its own
# minimal venv, so launchd never has to read from ~/Documents (TCC-protected).
# Re-run this script after pulling changes to update the installed copy.
#
# Usage: launchd/install.sh            (uses python3 from PATH)
#        PYTHON=/path/to/python3 launchd/install.sh
set -euo pipefail

LABEL="ch.stellaspeziali.oakwebcam"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
INSTALL_DIR="$HOME/Library/Application Support/OAKWebcam"
LOG_DIR="$HOME/Library/Logs/OAKWebcam"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DEPTHAI_REQ="$(grep -E '^depthai==' "$REPO_DIR/requirements.txt" || echo depthai)"
PYTHON="${PYTHON:-python3}"
DOMAIN="gui/$(id -u)"

# Don't pick up the repo venv's python if it happens to be activated.
if [[ -n "${VIRTUAL_ENV:-}" && "$(command -v "$PYTHON")" == "$VIRTUAL_ENV"/* ]]; then
    PYTHON="$("$PYTHON" -c 'import sys; print(sys._base_executable)')"
fi

echo "==> Using $("$PYTHON" --version) at $(command -v "$PYTHON")"

if pgrep -f "src.menu_bar_app|uvc_handler.py" >/dev/null; then
    echo "!! The menu bar app / uvc_handler is running. Quit it first:" >&2
    echo "   both must not hold the camera at the same time." >&2
    exit 1
fi

mkdir -p "$INSTALL_DIR" "$LOG_DIR" "$(dirname "$PLIST")"

if [[ ! -x "$INSTALL_DIR/venv/bin/python" ]]; then
    echo "==> Creating venv in $INSTALL_DIR/venv"
    "$PYTHON" -m venv "$INSTALL_DIR/venv"
fi
echo "==> Installing $DEPTHAI_REQ"
"$INSTALL_DIR/venv/bin/python" -m pip install --quiet --upgrade pip
"$INSTALL_DIR/venv/bin/python" -m pip install --quiet "$DEPTHAI_REQ"

echo "==> Copying service"
cp "$REPO_DIR/src/uvc_daemon.py" "$INSTALL_DIR/uvc_daemon.py"

echo "==> Writing $PLIST"
sed -e "s|__LABEL__|$LABEL|g" \
    -e "s|__INSTALL_DIR__|$INSTALL_DIR|g" \
    -e "s|__LOG_DIR__|$LOG_DIR|g" \
    "$REPO_DIR/launchd/$LABEL.plist.template" > "$PLIST"
plutil -lint "$PLIST" >/dev/null

echo "==> (Re)loading LaunchAgent"
launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
launchctl bootstrap "$DOMAIN" "$PLIST"

echo
echo "Installed. The OAK-D Lite will now become a webcam a few seconds after plug-in."
echo "  Log:     $LOG_DIR/oakwebcam.log"
echo "  Status:  launchctl print $DOMAIN/$LABEL | head -20"
echo "  Pause:   launchctl bootout $DOMAIN/$LABEL   (frees the device for TouchDesigner etc.)"
echo "  Resume:  launchctl bootstrap $DOMAIN $PLIST"
echo "  Remove:  launchd/uninstall.sh"
