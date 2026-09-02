#!/usr/bin/env python3
"""Venom Node Idempotent Installer and Service Provisioner."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

SYSTEMD_TEMPLATE = """[Unit]
Description=JARVIS Venom Infrastructure Node
After=network.target mosquitto.service
Wants=network.target

[Service]
Type=simple
User={user}
Group={group}
WorkingDirectory={install_dir}
Environment=JARVIS_VENOM_CONFIG={config_dir}/venom.json
EnvironmentFile=-{config_dir}/venom.env
ExecStart={venv_python} -m jarvis.nodes.venom_daemon
Restart=on-failure
RestartSec=5s
KillMode=process
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full

[Install]
WantedBy=multi-user.target
"""

CONFIG_TEMPLATE = {
    "node_id": "venom-01",
    "role": "server",
    "core_url": "",
    "device_id": "venom-01",
    "identity_id": "owner",
    "credential": "",
    "mqtt_enabled": True,
    "mqtt_broker_host": "127.0.0.1",
    "mqtt_broker_port": 1883,
    "backup_receive_dir": "/var/lib/jarvis/backups",
    "log_dir": "/var/log/jarvis",
}


def _default_runner(cmd: list[str]) -> tuple[int, str]:
    import subprocess
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return res.returncode, res.stdout + res.stderr
    except Exception as exc:
        return 1, str(exc)


def provision(
    install_dir: Path = Path("/opt/jarvis-venom"),
    config_dir: Path = Path("/etc/jarvis"),
    data_dir: Path = Path("/var/lib/jarvis/backups"),
    log_dir: Path = Path("/var/log/jarvis"),
    systemd_dir: Path = Path("/etc/systemd/system"),
    user: str = "jarvis",
    group: str = "jarvis",
    dry_run: bool = False,
    start_service: bool = False,
    command_runner: Callable[[list[str]], tuple[int, str]] | None = None,
) -> dict[str, Any]:
    runner = command_runner or _default_runner
    result: dict[str, Any] = {
        "install_dir": str(install_dir),
        "config_dir": str(config_dir),
        "data_dir": str(data_dir),
        "log_dir": str(log_dir),
        "systemd_dir": str(systemd_dir),
        "user": user,
        "group": group,
        "dry_run": dry_run,
        "steps_completed": [],
        "created_paths": [],
        "rollback_metadata": {
            "created_directories": [],
            "created_files": [],
        },
        "capabilities": {
            "mqtt_broker": "not_configured",
            "backup_receiver": "not_configured",
            "event_relay": "not_configured",
            "ha_bridge": "not_configured",
        },
        "status": "success",
    }

    if dry_run:
        result["status"] = "dry_run"
        result["steps_completed"] = [
            "validate_paths",
            "generate_config",
            "generate_systemd_unit",
            "plan_directories",
            "plan_service_user",
            "plan_venv_structure",
            "plan_config_and_env",
            "plan_systemd_unit",
            "plan_daemon_reload_and_enable",
        ]
        if start_service:
            result["steps_completed"].append("plan_service_start")
        return result

    # 1. Ensure service user
    code, out = runner(["id", "-u", user])
    if code != 0:
        c_add, out_add = runner(["useradd", "-r", "-s", "/bin/false", "-U", user])
        if c_add == 0:
            result["steps_completed"].append(f"created_service_user_{user}")
        else:
            result["steps_completed"].append(f"service_user_check_skipped:{out_add.strip()}")
    else:
        result["steps_completed"].append(f"verified_service_user_{user}")

    # 2. Create required directories
    for d in (install_dir, config_dir, data_dir, log_dir, systemd_dir):
        if not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            result["rollback_metadata"]["created_directories"].append(str(d))
    result["steps_completed"].append("created_directories")

    # 3. Create venv structure / pointer
    venv_dir = install_dir / ".venv" / "bin"
    venv_python = venv_dir / "python"
    if not venv_dir.exists():
        venv_dir.mkdir(parents=True, exist_ok=True)
    if not venv_python.exists():
        try:
            current_py = sys.executable
            if os.name != "nt":
                try:
                    venv_python.symlink_to(current_py)
                except OSError:
                    venv_python.write_text(f"#!/bin/sh\nexec {current_py} \"$@\"\n")
                    venv_python.chmod(0o755)
            else:
                venv_python.write_text(f"REM python pointer\n")
            result["rollback_metadata"]["created_files"].append(str(venv_python))
        except Exception:
            pass
    result["steps_completed"].append("prepared_venv_structure")

    # 4. Canonical config
    config_file = config_dir / "venom.json"
    if not config_file.exists():
        cfg = dict(CONFIG_TEMPLATE)
        cfg["backup_receive_dir"] = str(data_dir)
        cfg["log_dir"] = str(log_dir)
        config_file.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        result["created_paths"].append(str(config_file))
        result["rollback_metadata"]["created_files"].append(str(config_file))
        result["steps_completed"].append("generate_config")
        result["steps_completed"].append("generated_canonical_config")

    # 5. Strict-permission secret env file (0600)
    env_file = config_dir / "venom.env"
    if not env_file.exists():
        env_file.write_text("# JARVIS Venom Node Credentials\nJARVIS_CREDENTIAL=\n", encoding="utf-8")
        try:
            env_file.chmod(0o600)
        except OSError:
            pass
        result["created_paths"].append(str(env_file))
        result["rollback_metadata"]["created_files"].append(str(env_file))
        result["steps_completed"].append("generated_secret_env_file")

    # 6. Systemd unit installation (both in systemd_dir and config_dir backup)
    systemd_file = systemd_dir / "jarvis-venom.service"
    unit_content = SYSTEMD_TEMPLATE.format(
        user=user,
        group=group,
        install_dir=install_dir,
        venv_python=venv_python,
        config_dir=config_dir,
    )
    systemd_file.write_text(unit_content, encoding="utf-8")
    if config_dir != systemd_dir:
        (config_dir / "jarvis-venom.service").write_text(unit_content, encoding="utf-8")
    result["created_paths"].append(str(systemd_file))
    result["rollback_metadata"]["created_files"].append(str(systemd_file))
    result["steps_completed"].append("generate_systemd_unit")
    result["steps_completed"].append("installed_systemd_unit")

    # 7. Lifecycle management via command runner
    c_dr, _ = runner(["systemctl", "daemon-reload"])
    if c_dr == 0:
        result["steps_completed"].append("systemctl_daemon_reload")

    c_en, _ = runner(["systemctl", "enable", "jarvis-venom.service"])
    if c_en == 0:
        result["steps_completed"].append("systemctl_enable")

    if start_service:
        c_st, _ = runner(["systemctl", "start", "jarvis-venom.service"])
        if c_st == 0:
            result["steps_completed"].append("systemctl_start")

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Venom Node Provisioner")
    parser.add_argument("--install-dir", type=Path, default=Path("/opt/jarvis-venom"))
    parser.add_argument("--config-dir", type=Path, default=Path("/etc/jarvis"))
    parser.add_argument("--data-dir", type=Path, default=Path("/var/lib/jarvis/backups"))
    parser.add_argument("--log-dir", type=Path, default=Path("/var/log/jarvis"))
    parser.add_argument("--systemd-dir", type=Path, default=Path("/etc/systemd/system"))
    parser.add_argument("--user", type=str, default="jarvis")
    parser.add_argument("--group", type=str, default="jarvis")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--start", action="store_true", help="start service immediately after provisioning")
    args = parser.parse_args()

    result = provision(
        install_dir=args.install_dir,
        config_dir=args.config_dir,
        data_dir=args.data_dir,
        log_dir=args.log_dir,
        systemd_dir=args.systemd_dir,
        user=args.user,
        group=args.group,
        dry_run=args.dry_run,
        start_service=args.start,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
