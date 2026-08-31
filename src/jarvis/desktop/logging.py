"""Bounded, privacy-safe operational logging for the desktop shell."""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


class DesktopOperationalLogger:
    """Log only bounded lifecycle facts; callers never pass credentials/audio."""

    def __init__(self, path: Path | None = None) -> None:
        if path is None:
            local = os.getenv("LOCALAPPDATA", "").strip()
            base = Path(local) if local else Path.home() / "AppData" / "Local"
            path = base / "JARVIS" / "logs" / "desktop.log"
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._logger = logging.getLogger(f"jarvis.desktop.{id(self)}")
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False
        handler = RotatingFileHandler(self.path, maxBytes=256 * 1024, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        self._logger.addHandler(handler)
        self._handler = handler

    def info(self, message: str) -> None:
        self._logger.info(_safe(message))

    def warning(self, message: str) -> None:
        self._logger.warning(_safe(message))

    def close(self) -> None:
        self._logger.removeHandler(self._handler)
        self._handler.close()


def _safe(message: str) -> str:
    text = str(message).replace("\r", " ").replace("\n", " ")
    lowered = text.casefold()
    if any(marker in lowered for marker in ("credential", "secret", "password", "transcript", "raw audio", "tool args")):
        return "redacted_operational_message"
    return text[:300]
