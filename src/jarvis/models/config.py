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
    local_model: str
    openai_enabled: bool
    openai_model: str
    openai_timeout_seconds: float
    groq_enabled: bool
    groq_model: str
    groq_timeout_seconds: float
    groq_reasoning_effort: str
    gemini_enabled: bool
    gemini_model: str
    gemini_timeout_seconds: float
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
            provider=config.model_provider,
            primary_model=config.primary_model,
            fallback_model=config.fallback_model,
            local_model=config.local_model,
            openai_enabled=config.openai_enabled,
            openai_model=config.openai_model,
            openai_timeout_seconds=config.openai_timeout_seconds,
            groq_enabled=config.groq_enabled,
            groq_model=config.groq_model,
            groq_timeout_seconds=config.groq_timeout_seconds,
            groq_reasoning_effort=config.groq_reasoning_effort,
            gemini_enabled=config.gemini_enabled,
            gemini_model=config.gemini_model,
            gemini_timeout_seconds=config.gemini_timeout_seconds,
            ollama_base_url=config.ollama_base_url,
            llama_cpp_server_path=Path(config.llama_cpp_server_path).expanduser() if config.llama_cpp_server_path else None,
            llama_cpp_model_path=Path(config.llama_cpp_model_path).expanduser() if config.llama_cpp_model_path else None,
            llama_cpp_context_size=config.llama_cpp_context_size,
            llama_cpp_threads=config.llama_cpp_threads,
            llama_cpp_gpu_layers=config.llama_cpp_gpu_layers,
            local_model_autostart=config.local_model_autostart,
        )
