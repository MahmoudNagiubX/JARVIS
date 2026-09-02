#!/usr/bin/env bash
# Venom Node Preflight Check
set -euo pipefail

echo "=== JARVIS Venom Node Preflight ==="
python3 -c "import sys; print(f'Python version: {sys.version}')"
python3 scripts/venom/preflight.py
echo "=== Preflight OK ==="
