#!/usr/bin/env python3
"""Venom Node Health Check script."""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
from datetime import UTC, datetime


def probe_service_status(name: str) -> str:
    """Truthfully probe local service status using systemctl or socket, without constants."""
    systemctl = shutil.which("systemctl")
    if systemctl:
        try:
            res = subprocess.run(
                [systemctl, "is-active", name],
                capture_output=True,
                text=True,
                timeout=2,
            )
            out = res.stdout.strip().lower()
            if out in {"active", "running"}:
                return "active"
            elif out in {"inactive", "failed", "stopped"}:
                return out
        except Exception:
            pass

    if name == "mosquitto":
        try:
            with socket.create_connection(("127.0.0.1", 1883), timeout=0.5):
                return "active"
        except Exception:
            pass

    return "unknown"


def check_health() -> dict[str, object]:
    usage = shutil.disk_usage("/")
    total_gb = round(usage.total / (1024**3), 2)
    free_gb = round(usage.free / (1024**3), 2)
    used_gb = round(usage.used / (1024**3), 2)
    usage_pct = round((usage.used / usage.total) * 100, 2) if usage.total > 0 else 0.0

    mosq_status = probe_service_status("mosquitto")
    venom_status = probe_service_status("jarvis-venom")

    services = [
        {"name": "mosquitto", "status": mosq_status},
        {"name": "jarvis-venom", "status": venom_status},
    ]

    failed_services = [s for s in services if s["status"] == "failed"]
    all_active = all(s["status"] == "active" for s in services)

    if failed_services or free_gb < 0.5:
        status = "unhealthy"
    elif not all_active or usage_pct > 85.0 or free_gb < 1.0:
        status = "warning"
    else:
        status = "healthy"

    return {
        "checked_at": datetime.now(UTC).isoformat(),
        "status": status,
        "storage": {
            "total_gb": total_gb,
            "free_gb": free_gb,
            "used_gb": used_gb,
            "usage_percent": usage_pct,
        },
        "services": services,
    }


def main() -> int:
    health = check_health()
    print(json.dumps(health, indent=2))
    return 0 if health["status"] == "healthy" else 1


if __name__ == "__main__":
    sys.exit(main())
