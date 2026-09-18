"""Bounded model routing with normalized provider failures."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..config import JarvisConfig
from ..contracts import LLMRequest, LLMResponse
from ..events import Event, EventCategory, EventState
from .config import ModelGatewayConfig
from .health import ModelHealth
from .llama_runtime import LlamaCppRuntimeConfig, LlamaCppRuntimeSupervisor, LlamaRuntimeStatus
from .openai import OpenAIProvider
from .providers import LlamaCppProvider, MockModelProvider, ModelProviderError, OllamaProvider, UnavailableModelProvider
from .routing import ModelRoute, ModelSelection, default_selections


class ModelGateway:
    def __init__(
        self,
        config: JarvisConfig,
        providers: Mapping[str, object] | None = None,
        *,
        event_bus: Any | None = None,
        repository: Any | None = None,
    ) -> None:
        gateway_config = ModelGatewayConfig.from_config(config)
        self.config = gateway_config
        self._event_bus = event_bus
        self._repository = repository
        self.runtime_supervisor: LlamaCppRuntimeSupervisor | None = None
        provider_name = "llama_cpp" if gateway_config.provider == "gguf" else gateway_config.provider
        self.providers = dict(providers or {})
        if provider_name not in self.providers and gateway_config.provider in self.providers:
            self.providers[provider_name] = self.providers[gateway_config.provider]
        if not self.providers:
            if provider_name == "mock":
                self.providers["mock"] = MockModelProvider()
            elif provider_name == "ollama":
                self.providers["ollama"] = OllamaProvider(gateway_config.ollama_base_url)
            elif provider_name == "llama_cpp":
                try:
                    runtime_config = LlamaCppRuntimeConfig.from_config(
                        config,
                        repository_root=Path.cwd(),
                    )
                except ValueError as exc:
                    self.providers["llama_cpp"] = UnavailableModelProvider(str(exc))
                else:
                    self.runtime_supervisor = LlamaCppRuntimeSupervisor(runtime_config)
                    self.providers["llama_cpp"] = LlamaCppProvider(
                        runtime_config.endpoint,
                        model_alias=runtime_config.model_alias,
                    )
            elif provider_name == "openai":
                self.providers["openai"] = OpenAIProvider(
                    model=gateway_config.openai_model,
                    enabled=gateway_config.openai_enabled,
                    timeout_seconds=gateway_config.openai_timeout_seconds,
                )
            else:
                self.providers[provider_name] = UnavailableModelProvider("provider_adapter_not_configured")
        primary_model = gateway_config.openai_model if provider_name == "openai" else gateway_config.primary_model
        fallback_model = gateway_config.openai_model if provider_name == "openai" else gateway_config.fallback_model
        self.selections = default_selections(
            provider_name, primary_model, fallback_model
        )

    async def start(self) -> LlamaRuntimeStatus | None:
        """Optionally start an explicitly configured live local model."""

        if self.runtime_supervisor is None or not self.config.local_model_autostart:
            return None
        status = await self.runtime_supervisor.start()
        await self._emit_runtime("model.runtime.started", status, EventState.ACCEPTED)
        if status.ready:
            await self._emit_runtime("model.runtime.ready", status, EventState.COMPLETED)
        else:
            await self._emit_runtime("model.runtime.unavailable", status, EventState.FAILED)
        return status

    async def shutdown(self) -> LlamaRuntimeStatus | None:
        if self.runtime_supervisor is None:
            return None
        status = await self.runtime_supervisor.stop()
        await self._emit_runtime("model.runtime.stopped", status, EventState.COMPLETED)
        return status

    async def runtime_health(self) -> LlamaRuntimeStatus | None:
        if self.runtime_supervisor is None:
            return None
        return await self.runtime_supervisor.health()

    def selection(self, route: ModelRoute) -> ModelSelection:
        return self.selections[route]

    async def generate(self, request: LLMRequest, route: ModelRoute = ModelRoute.GENERAL_REASONING) -> LLMResponse:
        selection = self.selection(route)
        provider = self.providers.get(selection.provider)
        if provider is None:
            raise ModelProviderError("provider_not_registered")
        if hasattr(provider, "supports_route") and not provider.supports_route(route):
            raise ModelProviderError("model_route_unsupported")
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

    async def _emit_runtime(self, event_type: str, status: LlamaRuntimeStatus, state: EventState) -> None:
        payload = {
            "provider": status.provider,
            "ready": status.ready,
            "model_alias": status.model_alias,
            "owned": status.owned,
            "reason": status.reason,
        }
        event = Event.create(event_type, EventCategory.MODEL, correlation_id="model-runtime", payload=payload, state=state)
        if self._repository is not None:
            self._repository.append_event(event)
        if self._event_bus is not None:
            await self._event_bus.publish(event)
