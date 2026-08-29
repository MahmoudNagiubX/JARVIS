"""Configuration for the foundation bootstrap.

Configuration is intentionally small in Phase 02. Secrets remain outside this
object, and model/network clients are never contacted as a side effect of
import or bootstrap.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from ipaddress import ip_address
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True)
class JarvisConfig:
    """Validated runtime configuration with safe local defaults."""

    service_name: str = "jarvis"
    environment: str = "development"
    event_handler_timeout_seconds: float = 5.0
    database_path: str = "data/jarvis.sqlite3"
    model_provider: str = "mock"
    primary_model: str = "qwen3.5:4b"
    fallback_model: str = "qwen3.5-heretic:9b-q4km"
    ollama_base_url: str = "http://127.0.0.1:11434"
    max_agent_steps: int = 3

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
        database_path = os.getenv("JARVIS_DATABASE_PATH", defaults.database_path).strip()
        model_provider = os.getenv("JARVIS_MODEL_PROVIDER", defaults.model_provider).strip().lower()
        primary_model = os.getenv("JARVIS_PRIMARY_MODEL", defaults.primary_model).strip()
        fallback_model = os.getenv("JARVIS_FALLBACK_MODEL", defaults.fallback_model).strip()
        ollama_base_url = os.getenv("JARVIS_OLLAMA_BASE_URL", defaults.ollama_base_url).strip()
        max_steps_text = os.getenv("JARVIS_MAX_AGENT_STEPS", str(defaults.max_agent_steps))
        try:
            timeout = float(timeout_text)
        except ValueError as exc:
            raise ValueError("JARVIS_EVENT_HANDLER_TIMEOUT_SECONDS must be numeric") from exc
        try:
            max_agent_steps = int(max_steps_text)
        except ValueError as exc:
            raise ValueError("JARVIS_MAX_AGENT_STEPS must be an integer") from exc
        if not service_name:
            raise ValueError("service_name cannot be empty")
        if not environment:
            raise ValueError("environment cannot be empty")
        if timeout <= 0:
            raise ValueError("event handler timeout must be positive")
        if not database_path:
            raise ValueError("database_path cannot be empty")
        if model_provider not in {"mock", "ollama", "gguf", "llama_cpp"}:
            raise ValueError("JARVIS_MODEL_PROVIDER must be mock, ollama, gguf, or llama_cpp")
        if not primary_model or not fallback_model:
            raise ValueError("model aliases cannot be empty")
        _validate_loopback_http_url(ollama_base_url)
        if not 1 <= max_agent_steps <= 10:
            raise ValueError("max_agent_steps must be between 1 and 10")
        return cls(
            service_name,
            environment,
            timeout,
            database_path,
            model_provider,
            primary_model,
            fallback_model,
            ollama_base_url,
            max_agent_steps,
        )


def _validate_loopback_http_url(value: str) -> None:
    parsed = urlsplit(value)
    if parsed.scheme != "http" or parsed.username or parsed.password or parsed.path not in ("", "/"):
        raise ValueError("JARVIS_OLLAMA_BASE_URL must be a local unauthenticated HTTP origin")
    if parsed.hostname is None or parsed.port is None:
        raise ValueError("JARVIS_OLLAMA_BASE_URL must include a host and port")
    try:
        address = ip_address(parsed.hostname)
    except ValueError as exc:
        raise ValueError("JARVIS_OLLAMA_BASE_URL must use a loopback IP literal") from exc
    if not address.is_loopback:
        raise ValueError("JARVIS_OLLAMA_BASE_URL must remain loopback-only")
