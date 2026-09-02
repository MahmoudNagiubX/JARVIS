"""Lightweight Venom daemon process entry point for Linux infrastructure node."""

from __future__ import annotations

import json
import logging
import os
import shutil
import signal
import socket
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..network.validation import NetworkValidationError, validate_private_core_url
from .venom import VenomNode

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATHS = (
    Path("/etc/jarvis/venom.json"),
    Path("/opt/jarvis-venom/venom.json"),
)


class VenomDaemon:
    """Bounded infrastructure daemon running on Venom."""

    def __init__(
        self,
        config_path: str | Path | None = None,
        *,
        mode: str = "live-distributed",
        opener: Any = urlopen,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config_path = self._resolve_config_path(config_path)
        self.mode = mode
        self.opener = opener
        self.sleeper = sleeper
        self.node = VenomNode()
        self._running = False
        self._config: dict[str, Any] = {}
        self.consecutive_failures = 0
        self._load_config()

    @staticmethod
    def _resolve_config_path(config_path: str | Path | None) -> Path:
        if config_path is not None:
            return Path(config_path)
        env_path = os.getenv("JARVIS_VENOM_CONFIG")
        if env_path:
            return Path(env_path)
        for candidate in DEFAULT_CONFIG_PATHS:
            if candidate.exists():
                return candidate
        return DEFAULT_CONFIG_PATHS[0]

    def _load_config(self) -> None:
        if self.config_path.exists():
            try:
                self._config = json.loads(self.config_path.read_text(encoding="utf-8"))
            except Exception:
                self._config = {}
        else:
            self._config = {}

    @property
    def core_url(self) -> str | None:
        raw = os.getenv("JARVIS_CORE_URL") or self._config.get("core_url")
        if not raw:
            return None
        try:
            return validate_private_core_url(str(raw), mode=self.mode)
        except NetworkValidationError:
            return None

    @property
    def device_id(self) -> str:
        return os.getenv("JARVIS_DEVICE_ID") or str(self._config.get("device_id", "venom-01"))

    @property
    def identity_id(self) -> str:
        return os.getenv("JARVIS_IDENTITY_ID") or str(self._config.get("identity_id", "owner"))

    @property
    def credential(self) -> str | None:
        return os.getenv("JARVIS_CREDENTIAL") or self._config.get("credential")

    def collect_storage(self) -> dict[str, int]:
        try:
            target = str(self._config.get("backup_receive_dir", "/var/lib/jarvis/backups"))
            usage = shutil.disk_usage(target if Path(target).exists() else "/")
            return {
                "total_bytes": usage.total,
                "free_bytes": usage.free,
                "used_bytes": usage.used,
            }
        except Exception:
            return {"total_bytes": 0, "free_bytes": 0, "used_bytes": 0}

    def collect_services(self) -> list[dict[str, Any]]:
        services = [
            {"name": "jarvis-venom", "active": self._running, "status": "running" if self._running else "stopped"},
        ]
        mqtt_enabled = bool(self._config.get("mqtt_enabled", False))
        if not mqtt_enabled:
            services.append({
                "name": "mosquitto",
                "active": False,
                "status": "not_configured",
            })
        else:
            host = str(self._config.get("mqtt_broker_host", "127.0.0.1"))
            port = int(self._config.get("mqtt_broker_port", 1883))
            is_running = self._probe_tcp(host, port)
            services.append({
                "name": "mosquitto",
                "active": is_running,
                "status": "running" if is_running else "degraded",
            })
        return services

    def collect_capabilities(self) -> dict[str, str]:
        """Truthful status of Venom capabilities."""
        mqtt_enabled = bool(self._config.get("mqtt_enabled", False))
        if mqtt_enabled:
            host = str(self._config.get("mqtt_broker_host", "127.0.0.1"))
            port = int(self._config.get("mqtt_broker_port", 1883))
            is_running = self._probe_tcp(host, port)
            mqtt_status = "running" if is_running else "degraded"
        else:
            mqtt_status = "not_configured"

        return {
            "mqtt_broker": mqtt_status,
            "backup_receiver": "not_configured",
            "event_relay": "not_configured",
            "ha_bridge": "not_configured",
        }

    @staticmethod
    def _probe_tcp(host: str, port: int, timeout: float = 0.5) -> bool:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except Exception:
            return False

    def send_heartbeat(self) -> bool:
        url = self.core_url
        cred = self.credential
        if not url or not cred:
            self.consecutive_failures += 1
            self.node.set_health(False, "missing_core_url_or_credential")
            return False

        payload = {
            "healthy": True,
            "details": "daemon_running",
            "version": "phase17",
            "storage": self.collect_storage(),
            "services": self.collect_services(),
            "capabilities": self.collect_capabilities(),
        }
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cred}",
            "X-JARVIS-Device-ID": self.device_id,
            "X-JARVIS-Identity-ID": self.identity_id,
        }
        req = Request(f"{url}/nodes/venom/heartbeat", data=body, headers=headers, method="POST")
        try:
            with self.opener(req, timeout=5.0) as resp:
                if resp.status == 200:
                    self.consecutive_failures = 0
                    self.node.set_health(True, "heartbeat_acknowledged")
                    return True
                self.consecutive_failures += 1
                self.node.set_health(False, f"http_status_{resp.status}")
                return False
        except (HTTPError, URLError, OSError, TimeoutError) as exc:
            self.consecutive_failures += 1
            self.node.set_health(False, f"transport_error:{exc.__class__.__name__}")
            return False

    def calculate_next_delay(self, base_interval: float = 10.0, max_interval: float = 60.0) -> float:
        if self.consecutive_failures <= 0:
            return base_interval
        # Exponential backoff: base * 2^(failures - 1) capped at max_interval
        backoff = base_interval * (2 ** (self.consecutive_failures - 1))
        return min(max_interval, max(base_interval, backoff))

    def stop(self, *args: Any) -> None:
        self._running = False

    def run(
        self,
        poll_interval: float = 10.0,
        max_interval: float = 60.0,
        max_iterations: int | None = None,
    ) -> int:
        self._running = True
        try:
            signal.signal(signal.SIGTERM, self.stop)
            signal.signal(signal.SIGINT, self.stop)
        except (ValueError, AttributeError):
            pass

        self.node.set_health(True, "daemon_started")
        iterations = 0

        while self._running:
            self.send_heartbeat()
            iterations += 1
            if max_iterations is not None and iterations >= max_iterations:
                break
            delay = self.calculate_next_delay(base_interval=poll_interval, max_interval=max_interval)
            if not self._running:
                break
            self.sleeper(delay)

        if not self._running:
            self.node.set_health(False, "daemon_stopped")
        return 0


def main() -> int:
    daemon = VenomDaemon()
    return daemon.run()


if __name__ == "__main__":
    sys.exit(main())
