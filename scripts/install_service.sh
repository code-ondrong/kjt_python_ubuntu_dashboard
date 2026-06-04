#!/usr/bin/env bash
#
# install_service.sh — Deploy the Terminal Dashboard Monitoring System
#
# This script:
#   1. Creates the 'dashboard' system user
#   2. Copies files to /opt/system-monitor/
#   3. Installs Python dependencies
#   4. Installs and enables the systemd service
#   5. Disables getty@tty1 and keeps getty@tty2 as fallback
#
# Usage:
#   sudo bash scripts/install_service.sh
#

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
INSTALL_DIR="/opt/system-monitor"
SERVICE_NAME="dashboard.service"
SERVICE_SRC="${REPO_DIR}/systemd/${SERVICE_NAME}"
SERVICE_DST="/etc/systemd/system/${SERVICE_NAME}"

echo "==> Creating 'dashboard' system user (no login, no home)..."
if id "dashboard" &>/dev/null; then
    echo "    User 'dashboard' already exists, skipping."
else
    sudo useradd --system --no-create-home --shell /usr/sbin/nologin dashboard
fi

echo "==> Copying files to ${INSTALL_DIR}..."
sudo mkdir -p "${INSTALL_DIR}"
sudo cp "${REPO_DIR}/main.py"          "${INSTALL_DIR}/"
sudo cp "${REPO_DIR}/config.py"        "${INSTALL_DIR}/"
sudo cp "${REPO_DIR}/system_stats.py"  "${INSTALL_DIR}/"
sudo cp "${REPO_DIR}/gpu_stats.py"     "${INSTALL_DIR}/"
sudo cp "${REPO_DIR}/dashboard.py"     "${INSTALL_DIR}/"
sudo cp "${REPO_DIR}/requirements.txt" "${INSTALL_DIR}/"
sudo chown -R dashboard:dashboard "${INSTALL_DIR}"

echo "==> Creating Python virtual environment..."
sudo python3 -m venv "${INSTALL_DIR}/venv"
sudo "${INSTALL_DIR}/venv/bin/pip" install --upgrade pip

echo "==> Installing Python dependencies into venv..."
sudo "${INSTALL_DIR}/venv/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"

echo "==> Fixing venv permissions for 'dashboard' user..."
sudo chown -R dashboard:dashboard "${INSTALL_DIR}/venv"

echo "==> Installing systemd service..."
sudo cp "${SERVICE_SRC}" "${SERVICE_DST}"
sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"
sudo systemctl start  "${SERVICE_NAME}"

echo "==> Disabling getty@tty1 (dashboard will take over)..."
sudo systemctl disable getty@tty1 || true
sudo systemctl stop    getty@tty1 || true

echo "==> Keeping getty@tty2 enabled as fallback (Ctrl+Alt+F2)..."
sudo systemctl enable  getty@tty2 || true
sudo systemctl start   getty@tty2 || true

echo ""
echo "✅ Installation complete!"
echo "   - Dashboard runs on tty1 (Ctrl+Alt+F1)"
echo "   - Login fallback on tty2 (Ctrl+Alt+F2)"
echo "   - Service: sudo systemctl status ${SERVICE_NAME}"
echo "   - Logs:    sudo journalctl -u ${SERVICE_NAME} -f"
