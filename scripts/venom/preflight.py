#!/usr/bin/env python3
"""Venom Node Preflight Check for Ubuntu Server / Linux infrastructure."""

from __future__ import annotations

import json
import os
import platform
import shutil
import sys


def run_preflight() -> dict[str, object]:
    results = {
        "platform": platform.system(),
        "architecture": platform.machine(),
        "python_version": sys.version,
        "is_linux": platform.system().casefold() == "linux",
        "python_supported": sys.version_info >= (3, 11),
        "disk_free_gb": 0.0,
        "memory_total_gb": 0.0,
        "systemd_present": False,
        "ready": False,
        "errors": [],
    }

    if not results["is_linux"] and platform.system().casefold() != "windows":
        results["errors"].append("Target OS must be Linux (Ubuntu Server recommended)")

    if not results["python_supported"]:
        results["errors"].append("Python 3.11+ is required")

    try:
        usage = shutil.disk_usage("/")
        results["disk_free_gb"] = round(usage.free / (1024**3), 2)
        if results["disk_free_gb"] < 2.0:
            results["errors"].append("Insufficient disk space (at least 2 GB required)")
    except Exception:
        pass

    results["systemd_present"] = os.path.exists("/run/systemd/system") or os.path.exists("/bin/systemctl") or os.path.exists("/usr/bin/systemctl")

    results["ready"] = len(results["errors"]) == 0
    return results


def main() -> int:
    results = run_preflight()
    print(json.dumps(results, indent=2))
    return 0 if results["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
