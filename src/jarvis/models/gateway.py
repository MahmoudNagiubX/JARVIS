"""Bounded model routing with normalized provider failures."""

from __future__ import annotations

from collections.abc import Mapping

from ..config import JarvisConfig
from ..contracts import LLMRequest, LLMResponse
from .config import ModelGatewayConfig
from .health import ModelHealth
from .providers import MockModelProvider, ModelProviderError, OllamaProvider, UnavailableModelProvider
from .routing import ModelRoute, ModelSelection, default_selections


class ModelGateway:
    def __init__(self, config: JarvisConfig, providers: Mapping[str, object] | None = None) -> None:
        gateway_config = ModelGatewayConfig.from_config(config)
        self.config = gateway_config
        self.providers = dict(providers or {})
        if not self.providers:
            if gateway_config.provider == "mock":
                self.providers["mock"] = MockModelProvider()
            elif gateway_config.provider == "ollama":
                self.providers["ollama"] = OllamaProvider(gateway_config.ollama_base_url)
            else:
                self.providers[gateway_config.provider] = UnavailableModelProvider("provider_adapter_not_configured")
        self.selections = default_selections(
            gateway_config.provider, gateway_config.primary_model, gateway_config.fallback_model
        )

    def selection(self, route: ModelRoute) -> ModelSelection:
        return self.selections[route]

    async def generate(self, request: LLMRequest, route: ModelRoute = ModelRoute.GENERAL_REASONING) -> LLMResponse:
        selection = self.selection(route)
        provider = self.providers.get(selection.provider)
        if provider is None:
            raise ModelProviderError("provider_not_registered")
        routed = request if request.model == selection.model else request.__class__(
            request_id=request.request_id,
            messages=request.messages,
            model=selection.model,
            tools=request.tools,
            max_output_tokens=request.max_output_tokens,
            timeout_seconds=request.timeout_seconds,
        )
        response = await provider.generate(routed)
        if response.provider is None:
            return response.__class__(
                response.request_id, response.text, response.model, response.finish_reason,
                response.tool_calls, response.usage, selection.provider, response.model_digest,
            )
        return response

    async def health(self, route: ModelRoute = ModelRoute.GENERAL_REASONING) -> ModelHealth:
        selection = self.selection(route)
        provider = self.providers.get(selection.provider)
        if provider is None or not hasattr(provider, "health"):
            return ModelHealth.unavailable(selection.provider, "health_not_supported")
        return await provider.health(selection.model)
