#!/usr/bin/env bash
# Venom Node Safe Rollback and Uninstaller
set -euo pipefail

echo "=== Rolling back JARVIS Venom service ==="
if command -v systemctl >/dev/null 2>&1; then
    systemctl stop jarvis-venom || true
    systemctl disable jarvis-venom || true
    rm -f /etc/systemd/system/jarvis-venom.service
    systemctl daemon-reload || true
fi

echo "=== Removing installed service files (preserving backups) ==="
rm -rf /opt/jarvis-venom/.venv || true
echo "Backups preserved under /var/lib/jarvis/backups"
echo "=== Rollback complete ==="
