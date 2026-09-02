#!/usr/bin/env python3
"""Venom Node idempotent installer and service provisioner."""

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
    "trusted_lan_cidrs": [],
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


def _default_source_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def _failed(result: dict[str, Any], step: str, detail: str) -> dict[str, Any]:
    result["status"] = "failed"
    result["failed_step"] = step
    result["error"] = detail or "command_failed"
    return result


def _run_checked(runner: Callable[[list[str]], tuple[int, str]], command: list[str]) -> tuple[bool, str]:
    try:
        code, output = runner(command)
    except Exception as exc:
        return False, f"{exc.__class__.__name__}:{exc}"
    return code == 0, output.strip()


def _copy_bounded_source_package(source: Path, venv_root: Path) -> None:
    """Install the product package without a network or external build backend."""

    if os.name == "nt":
        purelib = venv_root / "Lib" / "site-packages"
    else:
        purelib = venv_root / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
    package_source = source / "src" / "jarvis"
    package_target = purelib / "jarvis"
    if not package_source.is_dir():
        raise OSError("canonical_local_package_missing")
    purelib.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        package_source,
        package_target,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )


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
    source_dir: Path | None = None,
    python_executable: Path | None = None,
) -> dict[str, Any]:
    runner = command_runner or _default_runner
    install_dir = Path(install_dir)
    config_dir = Path(config_dir)
    data_dir = Path(data_dir)
    log_dir = Path(log_dir)
    systemd_dir = Path(systemd_dir)
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
        "rollback_metadata": {"created_directories": [], "created_files": []},
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
            "plan_local_package_install",
            "plan_import_smoke",
            "plan_config_and_env",
            "plan_systemd_unit",
            "plan_daemon_reload_and_enable",
        ]
        if start_service:
            result["steps_completed"].append("plan_service_start")
        return result

    commands_applicable = command_runner is not None or os.name != "nt"

    # 1. Service user.
    if commands_applicable:
        ok, output = _run_checked(runner, ["id", "-u", user])
        if ok:
            result["steps_completed"].append(f"verified_service_user_{user}")
        else:
            created, create_output = _run_checked(runner, ["useradd", "-r", "-s", "/bin/false", "-U", user])
            if not created:
                return _failed(result, "service_user", create_output or output or "service_user_creation_failed")
            result["steps_completed"].append(f"created_service_user_{user}")
    else:
        result["steps_completed"].append("service_user_not_applicable_on_windows")

    # 2. Required directories.
    try:
        for directory in (install_dir, config_dir, data_dir, log_dir, systemd_dir):
            if not directory.exists():
                directory.mkdir(parents=True, exist_ok=True)
                result["rollback_metadata"]["created_directories"].append(str(directory))
    except OSError as exc:
        return _failed(result, "created_directories", str(exc))
    result["steps_completed"].append("created_directories")

    source = Path(source_dir or _default_source_dir()).expanduser().resolve()
    if not (source / "pyproject.toml").is_file() or not (source / "src" / "jarvis").is_dir():
        return _failed(result, "local_package_source", "canonical_local_package_source_missing")

    # 3. Canonical config.
    config_file = config_dir / "venom.json"
    if not config_file.exists():
        cfg = dict(CONFIG_TEMPLATE)
        cfg["backup_receive_dir"] = str(data_dir)
        cfg["log_dir"] = str(log_dir)
        try:
            config_file.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        except OSError as exc:
            return _failed(result, "generate_config", str(exc))
        result["created_paths"].append(str(config_file))
        result["rollback_metadata"]["created_files"].append(str(config_file))
        result["steps_completed"].extend(("generate_config", "generated_canonical_config"))

    # 4. Secret env file remains separate from the non-secret config.
    env_file = config_dir / "venom.env"
    if not env_file.exists():
        try:
            env_file.write_text("# JARVIS Venom Node Credentials\nJARVIS_CREDENTIAL=\n", encoding="utf-8")
            if os.name != "nt":
                env_file.chmod(0o600)
        except OSError as exc:
            return _failed(result, "generated_secret_env_file", str(exc))
        result["created_paths"].append(str(env_file))
        result["rollback_metadata"]["created_files"].append(str(env_file))
        result["steps_completed"].append("generated_secret_env_file")

    # 5. Real virtualenv and offline local package install.
    venv_root = install_dir / ".venv"
    venv_python = venv_root / "Scripts" / "python.exe" if os.name == "nt" else venv_root / "bin" / "python"
    if not venv_python.is_file():
        ok, output = _run_checked(runner, [str(python_executable or sys.executable), "-m", "venv", str(venv_root)])
        if not ok:
            return _failed(result, "create_virtualenv", output or "virtualenv_creation_failed")
        result["steps_completed"].append("create_virtualenv")
    else:
        result["steps_completed"].append("verified_virtualenv")

    ok, output = _run_checked(
        runner,
        [str(venv_python), "-m", "pip", "install", "--no-index", "--no-deps", "--no-build-isolation", str(source)],
    )
    if not ok:
        if not venv_python.is_file():
            return _failed(result, "install_local_package", output or "local_package_install_failed")
        try:
            _copy_bounded_source_package(source, venv_root)
        except OSError as exc:
            return _failed(result, "install_local_package", f"pip={output or 'failed'}; source_copy={exc}")
        result["package_install_mode"] = "bounded_source_copy"
    else:
        result["package_install_mode"] = "offline_pip"
    result["steps_completed"].append("install_local_package")

    ok, output = _run_checked(runner, [str(venv_python), "-c", "import jarvis; import jarvis.nodes.venom_daemon"])
    if not ok:
        return _failed(result, "import_smoke", output or "jarvis_import_smoke_failed")
    result["steps_completed"].append("import_smoke")

    # 6. Systemd unit is installed before lifecycle commands.
    systemd_file = systemd_dir / "jarvis-venom.service"
    unit_content = SYSTEMD_TEMPLATE.format(
        user=user,
        group=group,
        install_dir=install_dir,
        venv_python=venv_python,
        config_dir=config_dir,
    )
    try:
        systemd_file.write_text(unit_content, encoding="utf-8")
        if config_dir != systemd_dir:
            (config_dir / "jarvis-venom.service").write_text(unit_content, encoding="utf-8")
    except OSError as exc:
        return _failed(result, "generate_systemd_unit", str(exc))
    result["created_paths"].append(str(systemd_file))
    result["rollback_metadata"]["created_files"].append(str(systemd_file))
    result["steps_completed"].extend(("generate_systemd_unit", "installed_systemd_unit"))

    if not commands_applicable:
        result["steps_completed"].append("systemd_not_applicable_on_windows")
        return result

    # 7. Truthful systemd lifecycle.
    ok, output = _run_checked(runner, ["systemctl", "daemon-reload"])
    if not ok:
        return _failed(result, "systemctl_daemon_reload", output or "systemd_daemon_reload_failed")
    result["steps_completed"].append("systemctl_daemon_reload")

    ok, output = _run_checked(runner, ["systemctl", "enable", "jarvis-venom.service"])
    if not ok:
        return _failed(result, "systemctl_enable", output or "systemd_enable_failed")
    result["steps_completed"].append("systemctl_enable")

    if start_service:
        ok, output = _run_checked(runner, ["systemctl", "start", "jarvis-venom.service"])
        if not ok:
            return _failed(result, "systemctl_start", output or "systemd_start_failed")
        result["steps_completed"].append("systemctl_start")
        ok, output = _run_checked(runner, ["systemctl", "is-active", "--quiet", "jarvis-venom.service"])
        if not ok:
            return _failed(result, "health_verify", output or "venom_service_health_failed")
        result["steps_completed"].append("health_verify")

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
    return 0 if result["status"] in {"success", "dry_run"} else 1


if __name__ == "__main__":
    sys.exit(main())
