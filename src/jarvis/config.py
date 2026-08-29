"""Configuration for the foundation bootstrap.

Configuration is intentionally small in Phase 01. Loading secrets, models, and
network clients belongs to later adapters and is never a side effect of import
or bootstrap.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class JarvisConfig:
    """Validated runtime configuration with safe local defaults."""

    service_name: str = "jarvis"
    environment: str = "development"
    event_handler_timeout_seconds: float = 5.0

    @classmethod
    def from_env(cls) -> "JarvisConfig":
        """Read only non-secret bootstrap settings from the environment."""

        defaults = cls()
        service_name = os.getenv("JARVIS_SERVICE_NAME", defaults.service_name).strip()
        environment = os.getenv("JARVIS_ENVIRONMENT", defaults.environment).strip()
        timeout_text = os.getenv(
            "JARVIS_EVENT_HANDLER_TIMEOUT_SECONDS",
            str(defaults.event_handler_timeout_seconds),
        )
        try:
            timeout = float(timeout_text)
        except ValueError as exc:
            raise ValueError("JARVIS_EVENT_HANDLER_TIMEOUT_SECONDS must be numeric") from exc
        if not service_name:
            raise ValueError("service_name cannot be empty")
        if not environment:
            raise ValueError("environment cannot be empty")
        if timeout <= 0:
            raise ValueError("event handler timeout must be positive")
        return cls(service_name, environment, timeout)
