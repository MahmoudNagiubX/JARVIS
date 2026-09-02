# Venom Node Deployment & Provisioning

## Hardware & OS Target
- **Target Host**: Linux x86_64 host (`venom-server`, Ubuntu 24.04.4 LTS, Linux 6.8 kernel, interface `enp7s0`).
- **Physical Boundary Truth**: Managed via private configuration (`JARVIS_VENOM_HOST`). If unconfigured or non-interactive SSH fails, reported as `BLOCKED_WAITING_FOR_CONNECTION_DETAILS` without making unauthorized persistent remote changes.

## Provisioning Suite (`scripts/venom/`)
1. `preflight.py` / `preflight.sh`: Inspects platform architecture, Python 3.11+ runtime, disk space, and UFW firewall status.
2. `setup.py` / `install.sh`: Creates `/opt/jarvis-venom/`, creates a real venv, installs the canonical local package with no Internet dependency (falling back to a bounded source-package copy when offline build tooling is absent), runs `import jarvis; import jarvis.nodes.venom_daemon`, generates `jarvis-venom.service`, installs `venom.json`, and sets up log directories.
3. `firewall_setup.sh`: Enables UFW with default deny incoming and allows only private subnet traffic (ports 22, 1883, 8788).
4. `rollback.sh`: Idempotent rollback script that restores previous configuration while preserving durable SQLite backup archives.

Provisioning is truthful and idempotent: service-user, venv, local-package, import-smoke, systemd install/reload/enable, and optional service-health failures stop with a failed status and named step. `venom.json` keeps `trusted_lan_cidrs` empty by default; an owner-local override must be explicitly configured and is reported as `EXPLICIT_LOCAL_TRUST_OVERRIDE` rather than broadening the default private-LAN policy.
