"""Lightweight Venom daemon process entry point for Linux infrastructure node."""

from __future__ import annotations

import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any

from .venom import VenomNode


class VenomDaemon:
    """Bounded infrastructure daemon running on Venom."""

    def __init__(self, config_path: str | Path | None = None) -> None:
        self.config_path = Path(config_path or os.getenv("JARVIS_VENOM_CONFIG", "/opt/jarvis-venom/venom.json"))
        self.node = VenomNode()
        self._running = False
        self._config: dict[str, Any] = {}
        self._load_config()

    def _load_config(self) -> None:
        if self.config_path.exists():
            try:
                self._config = json.loads(self.config_path.read_text(encoding="utf-8"))
            except Exception:
                self._config = {}
        else:
            self._config = {}

    def stop(self, *args: Any) -> None:
        self._running = False

    def run(self, poll_interval: float = 10.0) -> int:
        self._running = True
        try:
            signal.signal(signal.SIGTERM, self.stop)
            signal.signal(signal.SIGINT, self.stop)
        except (ValueError, AttributeError):
            pass

        self.node.set_health(True, "daemon_started")

        while self._running:
            time.sleep(poll_interval)

        self.node.set_health(False, "daemon_stopped")
        return 0


def main() -> int:
    daemon = VenomDaemon()
    return daemon.run()


if __name__ == "__main__":
    sys.exit(main())
