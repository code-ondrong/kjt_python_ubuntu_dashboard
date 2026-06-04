#!/usr/bin/env bash
#
# uninstall_service.sh — Rollback the Terminal Dashboard installation
#
# This script:
#   1. Stops and disables the dashboard service
#   2. Removes the systemd unit file
#   3. Re-enables getty@tty1
#   4. Removes /opt/system-monitor/ (optional)
#   5. Removes the 'dashboard' user (optional)
#
# Usage:
#   sudo bash scripts/uninstall_service.sh
#

set -euo pipefail

SERVICE_NAME="dashboard.service"
SERVICE_DST="/etc/systemd/system/${SERVICE_NAME}"
INSTALL_DIR="/opt/system-monitor"

echo "==> Stopping and disabling ${SERVICE_NAME}..."
sudo systemctl stop  "${SERVICE_NAME}" 2>/dev/null || true
sudo systemctl disable "${SERVICE_NAME}" 2>/dev/null || true

echo "==> Removing systemd unit file..."
sudo rm -f "${SERVICE_DST}"
sudo systemctl daemon-reload

echo "==> Re-enabling getty@tty1..."
sudo systemctl enable getty@tty1 2>/dev/null || true
sudo systemctl start  getty@tty1 2>/dev/null || true

# ── Optional: remove installed files ─────────────────────────────────────
read -rp "Remove ${INSTALL_DIR}? [y/N] " confirm
if [[ "${confirm}" =~ ^[Yy]$ ]]; then
    echo "==> Removing ${INSTALL_DIR}..."
    sudo rm -rf "${INSTALL_DIR}"
fi

# ── Optional: remove dashboard user ──────────────────────────────────────
read -rp "Remove 'dashboard' system user? [y/N] " confirm
if [[ "${confirm}" =~ ^[Yy]$ ]]; then
    echo "==> Removing 'dashboard' user..."
    sudo userdel dashboard 2>/dev/null || true
fi

echo ""
echo "✅ Uninstall complete."
echo "   - getty@tty1 has been restored."
echo "   - Reboot or switch to tty1 (Ctrl+Alt+F1) to see the login prompt."
