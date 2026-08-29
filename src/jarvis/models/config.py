"""Model gateway configuration derived from the JARVIS config."""

from __future__ import annotations

from dataclasses import dataclass

from ..config import JarvisConfig


@dataclass(frozen=True, slots=True)
class ModelGatewayConfig:
    provider: str
    primary_model: str
    fallback_model: str
    ollama_base_url: str

    @classmethod
    def from_config(cls, config: JarvisConfig) -> "ModelGatewayConfig":
        return cls(config.model_provider, config.primary_model, config.fallback_model, config.ollama_base_url)
