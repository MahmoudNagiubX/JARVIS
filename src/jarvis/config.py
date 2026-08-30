"""Configuration for the foundation bootstrap.

Configuration is intentionally small. Secrets remain outside this
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
    deployment_profile: str = "development"
    runtime_role: str = "core"
    node_id: str = "windows-primary"
    core_url: str | None = None
    satellite_poll_interval_seconds: float = 15.0
    heartbeat_interval_seconds: float = 15.0
    voice_input_adapter: str = "noop"
    voice_output_adapter: str = "noop"

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
        ollama_base_url = os.getenv(
            "JARVIS_MODEL_LOOPBACK_ENDPOINT",
            os.getenv("JARVIS_OLLAMA_BASE_URL", defaults.ollama_base_url),
        ).strip()
        max_steps_text = os.getenv("JARVIS_MAX_AGENT_STEPS", str(defaults.max_agent_steps))
        deployment_profile = os.getenv("JARVIS_DEPLOYMENT_PROFILE", defaults.deployment_profile).strip().lower()
        runtime_role = os.getenv("JARVIS_RUNTIME_ROLE", defaults.runtime_role).strip().lower()
        node_id = os.getenv("JARVIS_NODE_ID", defaults.node_id).strip()
        core_url = os.getenv("JARVIS_CORE_URL", "").strip() or None
        poll_text = os.getenv("JARVIS_SATELLITE_POLL_INTERVAL_SECONDS", str(defaults.satellite_poll_interval_seconds))
        heartbeat_text = os.getenv("JARVIS_HEARTBEAT_INTERVAL_SECONDS", str(defaults.heartbeat_interval_seconds))
        voice_input_adapter = os.getenv("JARVIS_VOICE_INPUT_ADAPTER", defaults.voice_input_adapter).strip().lower()
        voice_output_adapter = os.getenv("JARVIS_VOICE_OUTPUT_ADAPTER", defaults.voice_output_adapter).strip().lower()
        try:
            timeout = float(timeout_text)
        except ValueError as exc:
            raise ValueError("JARVIS_EVENT_HANDLER_TIMEOUT_SECONDS must be numeric") from exc
        try:
            max_agent_steps = int(max_steps_text)
        except ValueError as exc:
            raise ValueError("JARVIS_MAX_AGENT_STEPS must be an integer") from exc
        try:
            satellite_poll_interval = float(poll_text)
            heartbeat_interval = float(heartbeat_text)
        except ValueError as exc:
            raise ValueError("satellite and heartbeat intervals must be numeric") from exc
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
        _validate_profile(deployment_profile, runtime_role, node_id, core_url, satellite_poll_interval, heartbeat_interval)
        return cls(
            service_name=service_name,
            environment=environment,
            event_handler_timeout_seconds=timeout,
            database_path=database_path,
            model_provider=model_provider,
            primary_model=primary_model,
            fallback_model=fallback_model,
            ollama_base_url=ollama_base_url,
            max_agent_steps=max_agent_steps,
            deployment_profile=deployment_profile,
            runtime_role=runtime_role,
            node_id=node_id,
            core_url=core_url,
            satellite_poll_interval_seconds=satellite_poll_interval,
            heartbeat_interval_seconds=heartbeat_interval,
            voice_input_adapter=voice_input_adapter,
            voice_output_adapter=voice_output_adapter,
        )

    @property
    def model_loopback_endpoint(self) -> str:
        """The existing loopback model endpoint under a provider-neutral name."""

        return self.ollama_base_url


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


def _validate_profile(
    profile: str,
    role: str,
    node_id: str,
    core_url: str | None,
    poll_interval: float,
    heartbeat_interval: float,
) -> None:
    if profile not in {"test", "development", "live-workstation", "live-distributed"}:
        raise ValueError("JARVIS_DEPLOYMENT_PROFILE is unsupported")
    if role not in {"core", "satellite"}:
        raise ValueError("JARVIS_RUNTIME_ROLE must be core or satellite")
    if not node_id or len(node_id) > 100 or any(char.isspace() for char in node_id):
        raise ValueError("JARVIS_NODE_ID must be a bounded non-empty token")
    if poll_interval <= 0 or poll_interval > 300 or heartbeat_interval <= 0 or heartbeat_interval > 300:
        raise ValueError("satellite and heartbeat intervals must be between 0 and 300 seconds")
    if role == "satellite" and not core_url:
        raise ValueError("JARVIS_CORE_URL is required for satellite runtime role")
    if core_url:
        parsed = urlsplit(core_url)
        if parsed.scheme != "http" or parsed.username or parsed.password or parsed.path not in ("", "/"):
            raise ValueError("JARVIS_CORE_URL must be a loopback HTTP origin")
        if parsed.hostname is None or parsed.port is None:
            raise ValueError("JARVIS_CORE_URL must include a loopback host and port")
        try:
            address = ip_address(parsed.hostname)
        except ValueError as exc:
            raise ValueError("JARVIS_CORE_URL must use a loopback IP literal") from exc
        if not address.is_loopback:
            raise ValueError("JARVIS_CORE_URL must remain loopback-only")
