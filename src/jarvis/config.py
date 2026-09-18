"""Configuration for the foundation bootstrap.

Configuration is intentionally small. Secrets remain outside this
object, and model/network clients are never contacted as a side effect of
import or bootstrap.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from ipaddress import ip_address
from urllib.parse import urlsplit


def default_llama_cpp_threads() -> int:
    """Return a safe bounded default for the current host.

    Hosted Windows runners may expose fewer logical CPUs than the historical
    eight-thread workstation default. The configured value must remain within
    the host bound, so choose the historical ceiling without making a small
    machine invalid at import/bootstrap time.
    """

    return max(1, min(8, os.cpu_count() or 1))


@dataclass(frozen=True, slots=True)
class JarvisConfig:
    """Validated runtime configuration with safe local defaults."""

    service_name: str = "jarvis"
    environment: str = "development"
    event_handler_timeout_seconds: float = 5.0
    database_path: str = "data/jarvis.sqlite3"
    model_provider: str = "mock"
    primary_model: str = "Qwen3.5-4B-Heretic"
    fallback_model: str = "Qwen3.5-4B-Heretic"
    # The hybrid route uses the owner-provisioned Heretic alias while the
    # legacy primary/fallback fields remain compatible with existing local
    # Ollama/llama.cpp profiles and tests.
    local_model: str = "Qwen3.5-4B-Heretic"
    groq_enabled: bool = False
    groq_model: str = "openai/gpt-oss-120b"
    groq_timeout_seconds: float = 30.0
    groq_reasoning_effort: str = "low"
    gemini_enabled: bool = False
    gemini_model: str = "gemini-3.5-flash"
    gemini_timeout_seconds: float = 45.0
    codex_worker_enabled: bool = False
    ollama_base_url: str = "http://127.0.0.1:11434"
    llama_cpp_server_path: str | None = None
    llama_cpp_model_path: str | None = None
    llama_cpp_context_size: int = 4096
    llama_cpp_threads: int = field(default_factory=default_llama_cpp_threads)
    llama_cpp_gpu_layers: int | None = None
    local_model_autostart: bool = False
    max_agent_steps: int = 3
    deployment_profile: str = "development"
    runtime_role: str = "core"
    node_id: str = "windows-primary"
    core_url: str | None = None
    satellite_poll_interval_seconds: float = 15.0
    heartbeat_interval_seconds: float = 15.0
    voice_input_adapter: str = "noop"
    voice_output_adapter: str = "noop"
    desktop_awareness_enabled: bool = False
    file_access_roots: tuple[str, ...] = ()
    ocr_model_dir: str | None = None
    browser_backend: str = "local"
    browser_executable_path: str | None = None
    browser_headless: bool = True
    browser_owner_persistent_opt_in: bool = False
    browser_profile_root: str | None = None
    installed_apps_config_path: str = "data/installed_apps.json"

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
        model_provider = os.getenv("JARVIS_MODEL_PROVIDER", "hybrid").strip().lower()
        primary_model = os.getenv("JARVIS_PRIMARY_MODEL", defaults.primary_model).strip()
        fallback_model = os.getenv("JARVIS_FALLBACK_MODEL", defaults.fallback_model).strip()
        local_model = os.getenv("JARVIS_LOCAL_MODEL", defaults.local_model).strip()
        groq_enabled_text = os.getenv(
            "JARVIS_GROQ_ENABLED",
            "true" if defaults.groq_enabled else "false",
        ).strip().lower()
        groq_model = os.getenv("JARVIS_GROQ_MODEL", defaults.groq_model).strip()
        groq_timeout_text = os.getenv("JARVIS_GROQ_TIMEOUT_SECONDS", str(defaults.groq_timeout_seconds)).strip()
        groq_reasoning_effort = os.getenv(
            "JARVIS_GROQ_REASONING_EFFORT",
            defaults.groq_reasoning_effort,
        ).strip().lower()
        gemini_enabled_text = os.getenv(
            "JARVIS_GEMINI_ENABLED",
            "true" if defaults.gemini_enabled else "false",
        ).strip().lower()
        gemini_model = os.getenv("JARVIS_GEMINI_MODEL", defaults.gemini_model).strip()
        gemini_timeout_text = os.getenv(
            "JARVIS_GEMINI_TIMEOUT_SECONDS",
            str(defaults.gemini_timeout_seconds),
        ).strip()
        codex_worker_enabled_text = os.getenv(
            "JARVIS_CODEX_WORKER_ENABLED",
            "true" if defaults.codex_worker_enabled else "false",
        ).strip().lower()
        ollama_base_url = os.getenv(
            "JARVIS_MODEL_LOOPBACK_ENDPOINT",
            os.getenv("JARVIS_OLLAMA_BASE_URL", defaults.ollama_base_url),
        ).strip()
        llama_cpp_server_path = os.getenv("JARVIS_LLAMA_CPP_SERVER_PATH", "").strip() or None
        llama_cpp_model_path = os.getenv("JARVIS_LLAMA_CPP_MODEL_PATH", "").strip() or None
        context_text = os.getenv("JARVIS_LLAMA_CPP_CONTEXT_SIZE", str(defaults.llama_cpp_context_size)).strip()
        threads_text = os.getenv("JARVIS_LLAMA_CPP_THREADS", str(defaults.llama_cpp_threads)).strip()
        gpu_layers_text = os.getenv("JARVIS_LLAMA_CPP_GPU_LAYERS", "").strip()
        autostart_text = os.getenv("JARVIS_LOCAL_MODEL_AUTOSTART", "false").strip().lower()
        max_steps_text = os.getenv("JARVIS_MAX_AGENT_STEPS", str(defaults.max_agent_steps))
        deployment_profile = os.getenv("JARVIS_DEPLOYMENT_PROFILE", defaults.deployment_profile).strip().lower()
        runtime_role = os.getenv("JARVIS_RUNTIME_ROLE", defaults.runtime_role).strip().lower()
        node_id = os.getenv("JARVIS_NODE_ID", defaults.node_id).strip()
        core_url = os.getenv("JARVIS_CORE_URL", "").strip() or None
        poll_text = os.getenv("JARVIS_SATELLITE_POLL_INTERVAL_SECONDS", str(defaults.satellite_poll_interval_seconds))
        heartbeat_text = os.getenv("JARVIS_HEARTBEAT_INTERVAL_SECONDS", str(defaults.heartbeat_interval_seconds))
        voice_input_adapter = os.getenv("JARVIS_VOICE_INPUT_ADAPTER", defaults.voice_input_adapter).strip().lower()
        voice_output_adapter = os.getenv("JARVIS_VOICE_OUTPUT_ADAPTER", defaults.voice_output_adapter).strip().lower()
        awareness_text = os.getenv("JARVIS_DESKTOP_AWARENESS_ENABLED", "false").strip().lower()
        file_access_roots_text = os.getenv("JARVIS_FILE_ACCESS_ROOTS", "").strip()
        file_access_roots = tuple(
            entry.strip() for entry in file_access_roots_text.split(os.pathsep) if entry.strip()
        ) if file_access_roots_text else ()
        # No implicit home-directory fallback (R18B05-001, Batch 06) - an
        # unset/empty value means "OCR models unavailable", never "use
        # EasyOCR's own ~/.EasyOCR default".
        ocr_model_dir = os.getenv("JARVIS_OCR_MODEL_DIR", "").strip() or None
        browser_backend = os.getenv("JARVIS_BROWSER_BACKEND", defaults.browser_backend).strip().lower()
        browser_executable_path = os.getenv("JARVIS_BROWSER_EXECUTABLE_PATH", "").strip() or None
        browser_headless_text = os.getenv(
            "JARVIS_BROWSER_HEADLESS",
            "true" if defaults.browser_headless else "false",
        ).strip().lower()
        browser_owner_opt_in_text = os.getenv(
            "JARVIS_BROWSER_OWNER_PERSISTENT",
            "true" if defaults.browser_owner_persistent_opt_in else "false",
        ).strip().lower()
        browser_profile_root = os.getenv("JARVIS_BROWSER_PROFILE_ROOT", "").strip() or None
        installed_apps_config_path = os.getenv("JARVIS_INSTALLED_APPS_CONFIG", defaults.installed_apps_config_path).strip()
        try:
            timeout = float(timeout_text)
        except ValueError as exc:
            raise ValueError("JARVIS_EVENT_HANDLER_TIMEOUT_SECONDS must be numeric") from exc
        try:
            max_agent_steps = int(max_steps_text)
        except ValueError as exc:
            raise ValueError("JARVIS_MAX_AGENT_STEPS must be an integer") from exc
        try:
            groq_timeout = float(groq_timeout_text)
            gemini_timeout = float(gemini_timeout_text)
        except ValueError as exc:
            raise ValueError("JARVIS cloud provider timeouts must be numeric") from exc
        try:
            llama_cpp_context_size = int(context_text)
            llama_cpp_threads = int(threads_text)
            llama_cpp_gpu_layers = int(gpu_layers_text) if gpu_layers_text else None
        except ValueError as exc:
            raise ValueError("llama.cpp context, threads, and gpu layers must be integers") from exc
        try:
            satellite_poll_interval = float(poll_text)
            heartbeat_interval = float(heartbeat_text)
        except ValueError as exc:
            raise ValueError("satellite and heartbeat intervals must be numeric") from exc
        if awareness_text not in {"true", "false", "1", "0", "yes", "no", "on", "off"}:
            raise ValueError("JARVIS_DESKTOP_AWARENESS_ENABLED must be boolean")
        boolean_values = {"true", "false", "1", "0", "yes", "no", "on", "off"}
        if groq_enabled_text not in boolean_values:
            raise ValueError("JARVIS_GROQ_ENABLED must be boolean")
        if gemini_enabled_text not in boolean_values:
            raise ValueError("JARVIS_GEMINI_ENABLED must be boolean")
        if codex_worker_enabled_text not in boolean_values:
            raise ValueError("JARVIS_CODEX_WORKER_ENABLED must be boolean")
        if browser_headless_text not in boolean_values:
            raise ValueError("JARVIS_BROWSER_HEADLESS must be boolean")
        if browser_owner_opt_in_text not in boolean_values:
            raise ValueError("JARVIS_BROWSER_OWNER_PERSISTENT must be boolean")
        if not service_name:
            raise ValueError("service_name cannot be empty")
        if not environment:
            raise ValueError("environment cannot be empty")
        if timeout <= 0:
            raise ValueError("event handler timeout must be positive")
        if not database_path:
            raise ValueError("database_path cannot be empty")
        if not installed_apps_config_path or len(installed_apps_config_path) > 1_000:
            raise ValueError("JARVIS_INSTALLED_APPS_CONFIG must be a bounded non-empty path")
        if model_provider not in {"mock", "ollama", "gguf", "llama_cpp", "hybrid"}:
            raise ValueError("JARVIS_MODEL_PROVIDER must be mock, ollama, gguf, llama_cpp, or hybrid")
        if browser_backend not in {"local", "playwright"}:
            raise ValueError("JARVIS_BROWSER_BACKEND must be local or playwright")
        if not primary_model or not fallback_model:
            raise ValueError("model aliases cannot be empty")
        for name, value in (
            ("JARVIS_LOCAL_MODEL", local_model),
            ("JARVIS_GROQ_MODEL", groq_model),
            ("JARVIS_GEMINI_MODEL", gemini_model),
        ):
            if not value or len(value) > 200 or any(char.isspace() for char in value):
                raise ValueError(f"{name} must be a bounded non-empty token")
        if not 1.0 <= groq_timeout <= 180.0 or not 1.0 <= gemini_timeout <= 180.0:
            raise ValueError("JARVIS cloud provider timeouts must be between 1 and 180")
        if groq_reasoning_effort not in {"none", "default", "minimal", "low", "medium", "high", "xhigh", "max"}:
            raise ValueError("JARVIS_GROQ_REASONING_EFFORT is unsupported")
        if not 1024 <= llama_cpp_context_size <= 32768:
            raise ValueError("JARVIS_LLAMA_CPP_CONTEXT_SIZE must be between 1024 and 32768")
        logical_cpus = os.cpu_count() or 1
        if not 1 <= llama_cpp_threads <= logical_cpus:
            raise ValueError("JARVIS_LLAMA_CPP_THREADS must be within logical CPU count")
        if llama_cpp_gpu_layers is not None and not -1 <= llama_cpp_gpu_layers <= 256:
            raise ValueError("JARVIS_LLAMA_CPP_GPU_LAYERS must be -1 or between 0 and 256")
        if autostart_text not in {"true", "false", "1", "0", "yes", "no", "on", "off"}:
            raise ValueError("JARVIS_LOCAL_MODEL_AUTOSTART must be boolean")
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
            local_model=local_model,
            groq_enabled=groq_enabled_text in {"true", "1", "yes", "on"},
            groq_model=groq_model,
            groq_timeout_seconds=groq_timeout,
            groq_reasoning_effort=groq_reasoning_effort,
            gemini_enabled=gemini_enabled_text in {"true", "1", "yes", "on"},
            gemini_model=gemini_model,
            gemini_timeout_seconds=gemini_timeout,
            codex_worker_enabled=codex_worker_enabled_text in {"true", "1", "yes", "on"},
            ollama_base_url=ollama_base_url,
            llama_cpp_server_path=llama_cpp_server_path,
            llama_cpp_model_path=llama_cpp_model_path,
            llama_cpp_context_size=llama_cpp_context_size,
            llama_cpp_threads=llama_cpp_threads,
            llama_cpp_gpu_layers=llama_cpp_gpu_layers,
            local_model_autostart=autostart_text in {"true", "1", "yes", "on"},
            max_agent_steps=max_agent_steps,
            deployment_profile=deployment_profile,
            runtime_role=runtime_role,
            node_id=node_id,
            core_url=core_url,
            satellite_poll_interval_seconds=satellite_poll_interval,
            heartbeat_interval_seconds=heartbeat_interval,
            voice_input_adapter=voice_input_adapter,
            voice_output_adapter=voice_output_adapter,
            desktop_awareness_enabled=awareness_text in {"true", "1", "yes", "on"},
            file_access_roots=file_access_roots,
            ocr_model_dir=ocr_model_dir,
            browser_backend=browser_backend,
            browser_executable_path=browser_executable_path,
            browser_headless=browser_headless_text in {"true", "1", "yes", "on"},
            browser_owner_persistent_opt_in=browser_owner_opt_in_text in {"true", "1", "yes", "on"},
            browser_profile_root=browser_profile_root,
            installed_apps_config_path=installed_apps_config_path,
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


def validate_loopback_http_origin(value: str) -> tuple[str, int]:
    """Validate and return a literal loopback HTTP host/port pair."""

    parsed = urlsplit(value)
    if parsed.scheme != "http" or parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("llama.cpp endpoint must be a loopback HTTP origin")
    if parsed.hostname is None or parsed.port is None:
        raise ValueError("llama.cpp endpoint must include a loopback host and port")
    try:
        address = ip_address(parsed.hostname)
    except ValueError as exc:
        raise ValueError("llama.cpp endpoint must use a loopback IP literal") from exc
    if not address.is_loopback:
        raise ValueError("llama.cpp endpoint must remain loopback-only")
    return parsed.hostname, parsed.port


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
        if profile == "live-distributed":
            from .network.validation import NetworkValidationError, validate_private_core_url
            try:
                validate_private_core_url(core_url, mode="live-distributed")
            except NetworkValidationError as exc:
                raise ValueError(f"JARVIS_CORE_URL validation failed: {exc}") from exc
        else:
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
