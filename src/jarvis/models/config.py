"""Model gateway configuration derived from the JARVIS config."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import JarvisConfig


@dataclass(frozen=True, slots=True)
class ModelGatewayConfig:
    provider: str
    primary_model: str
    fallback_model: str
    openai_enabled: bool
    openai_model: str
    openai_timeout_seconds: float
    ollama_base_url: str
    llama_cpp_server_path: Path | None
    llama_cpp_model_path: Path | None
    llama_cpp_context_size: int
    llama_cpp_threads: int
    llama_cpp_gpu_layers: int | None
    local_model_autostart: bool

    @classmethod
    def from_config(cls, config: JarvisConfig) -> "ModelGatewayConfig":
        return cls(
            config.model_provider,
            config.primary_model,
            config.fallback_model,
            config.openai_enabled,
            config.openai_model,
            config.openai_timeout_seconds,
            config.ollama_base_url,
            Path(config.llama_cpp_server_path).expanduser() if config.llama_cpp_server_path else None,
            Path(config.llama_cpp_model_path).expanduser() if config.llama_cpp_model_path else None,
            config.llama_cpp_context_size,
            config.llama_cpp_threads,
            config.llama_cpp_gpu_layers,
            config.local_model_autostart,
        )
