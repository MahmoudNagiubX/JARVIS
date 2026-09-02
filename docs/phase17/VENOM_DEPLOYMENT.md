# Venom Node Deployment & Provisioning

## Hardware & OS Target
- **Target Host**: Linux x86_64 host (`venom-server`, Ubuntu 24.04.4 LTS, Linux 6.8 kernel, interface `enp7s0`).
- **Physical Boundary Truth**: Managed via private configuration (`JARVIS_VENOM_HOST`). If unconfigured or non-interactive SSH fails, reported as `BLOCKED_WAITING_FOR_CONNECTION_DETAILS` without making unauthorized persistent remote changes.

## Provisioning Suite (`scripts/venom/`)
1. `preflight.py` / `preflight.sh`: Inspects platform architecture, Python 3.11+ runtime, disk space, and UFW firewall status.
2. `setup.py` / `install.sh`: Creates `/opt/jarvis-venom/`, generates `jarvis-venom.service` systemd unit, installs `venom.json` configuration, and sets up log directories.
3. `firewall_setup.sh`: Enables UFW with default deny incoming and allows only private subnet traffic (ports 22, 1883, 8788).
4. `rollback.sh`: Idempotent rollback script that restores previous configuration while preserving durable SQLite backup archives.
