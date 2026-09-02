#!/usr/bin/env bash
# Venom Node LAN-only UFW Firewall Setup
set -euo pipefail

echo "=== Configuring UFW for Venom Node (LAN only) ==="
# Default deny incoming, allow outgoing
ufw default deny incoming
ufw default allow outgoing

# Allow local LAN SSH (e.g. 192.168.0.0/16 or 10.0.0.0/8)
ufw allow from 192.168.0.0/16 to any port 22 proto tcp comment 'LAN SSH'
ufw allow from 10.0.0.0/8 to any port 22 proto tcp comment 'LAN SSH'

# Allow local Mosquitto MQTT
ufw allow from 192.168.0.0/16 to any port 1883 proto tcp comment 'LAN MQTT'
ufw allow from 10.0.0.0/8 to any port 1883 proto tcp comment 'LAN MQTT'

echo "=== UFW configuration ready (enable with 'ufw enable') ==="
