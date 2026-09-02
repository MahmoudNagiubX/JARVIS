#!/usr/bin/env python3
"""Venom Node Idempotent Installer and Service Provisioner."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

SYSTEMD_TEMPLATE = """[Unit]
Description=JARVIS Venom Infrastructure Node
After=network.target mosquitto.service
Wants=network.target

[Service]
Type=simple
User={user}
Group={group}
WorkingDirectory={install_dir}
ExecStart={venv_python} -m jarvis.nodes.venom_daemon
Restart=on-failure
RestartSec=5s
KillMode=process
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
EnvironmentFile=-{config_dir}/venom.env

[Install]
WantedBy=multi-user.target
"""

CONFIG_TEMPLATE = {
    "node_id": "venom-01",
    "role": "server",
    "core_url": "http://127.0.0.1:8787",
    "mqtt_enabled": True,
    "mqtt_broker_host": "127.0.0.1",
    "mqtt_broker_port": 1883,
    "backup_receive_dir": "/var/lib/jarvis/backups",
    "log_dir": "/var/log/jarvis",
}


def provision(
    install_dir: Path,
    config_dir: Path,
    user: str = "jarvis",
    dry_run: bool = False,
) -> dict[str, object]:
    result = {
        "install_dir": str(install_dir),
        "config_dir": str(config_dir),
        "user": user,
        "dry_run": dry_run,
        "steps_completed": [],
    }

    if dry_run:
        result["steps_completed"] = [
            "validate_paths",
            "generate_config",
            "generate_systemd_unit",
        ]
        return result

    install_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)
    result["steps_completed"].append("created_directories")

    config_file = config_dir / "venom.json"
    if not config_file.exists():
        config_file.write_text(json.dumps(CONFIG_TEMPLATE, indent=2))
        result["steps_completed"].append("generated_default_config")

    systemd_file = config_dir / "jarvis-venom.service"
    unit_content = SYSTEMD_TEMPLATE.format(
        user=user,
        group=user,
        install_dir=install_dir,
        venv_python=install_dir / ".venv" / "bin" / "python",
        config_dir=config_dir,
    )
    systemd_file.write_text(unit_content)
    result["steps_completed"].append("generated_systemd_unit")

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Venom Node Provisioner")
    parser.add_argument("--install-dir", type=Path, default=Path("/opt/jarvis-venom"))
    parser.add_argument("--config-dir", type=Path, default=Path("/etc/jarvis"))
    parser.add_argument("--user", type=str, default="jarvis")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = provision(args.install_dir, args.config_dir, args.user, args.dry_run)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
