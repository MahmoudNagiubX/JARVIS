#!/usr/bin/env bash
# Venom Node Idempotent Installer
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/jarvis-venom}"
CONFIG_DIR="${CONFIG_DIR:-/etc/jarvis}"
SERVICE_USER="${SERVICE_USER:-jarvis}"

echo "=== Installing JARVIS Venom Node ==="
python3 scripts/venom/setup.py --install-dir "${INSTALL_DIR}" --config-dir "${CONFIG_DIR}" --user "${SERVICE_USER}"
echo "=== Setup complete ==="
