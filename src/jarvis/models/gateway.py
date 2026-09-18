"""Bounded model routing with normalized provider failures."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from ..config import JarvisConfig
from ..contracts import LLMMessage, LLMRequest, LLMResponse
from ..events import Event, EventCategory, EventState
from .cloud import GeminiProvider, GroqProvider
from .config import ModelGatewayConfig
from .health import ModelHealth
from .llama_runtime import LlamaCppRuntimeConfig, LlamaCppRuntimeSupervisor, LlamaRuntimeStatus
from .openai import OpenAIProvider
from .providers import LlamaCppProvider, MockModelProvider, ModelProviderError, OllamaProvider, UnavailableModelProvider
from .routing import CapabilityRouter, ModelRoute, ModelSelection, default_selections, hybrid_selections


LOGGER = logging.getLogger(__name__)


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
        self.capability_router = CapabilityRouter()
        self._hybrid_models = {
            "local": gateway_config.local_model,
            "groq": gateway_config.groq_model,
            "gemini": gateway_config.gemini_model,
        }
        if provider_name == "hybrid":
            self._configure_hybrid(config, gateway_config)
        elif not self.providers:
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
        if provider_name == "hybrid":
            self.selections = hybrid_selections(
                gateway_config.local_model,
                gateway_config.groq_model,
                gateway_config.gemini_model,
            )
        else:
            primary_model = gateway_config.openai_model if provider_name == "openai" else gateway_config.primary_model
            fallback_model = gateway_config.openai_model if provider_name == "openai" else gateway_config.fallback_model
            self.selections = default_selections(provider_name, primary_model, fallback_model)

    def _configure_hybrid(self, config: JarvisConfig, gateway_config: ModelGatewayConfig) -> None:
        """Build all three adapters behind this gateway without contacting them."""

        if "local" not in self.providers and "ollama" in self.providers:
            self.providers["local"] = self.providers["ollama"]
        if "local" not in self.providers:
            if gateway_config.llama_cpp_server_path is not None and gateway_config.llama_cpp_model_path is not None:
                try:
                    local_config = replace(
                        config,
                        model_provider="llama_cpp",
                        primary_model=gateway_config.local_model,
                    )
                    runtime_config = LlamaCppRuntimeConfig.from_config(
                        local_config,
                        repository_root=Path.cwd(),
                    )
                except ValueError as exc:
                    self.providers["local"] = UnavailableModelProvider(str(exc))
                else:
                    self.runtime_supervisor = LlamaCppRuntimeSupervisor(runtime_config)
                    self.providers["local"] = LlamaCppProvider(
                        runtime_config.endpoint,
                        model_alias=runtime_config.model_alias,
                    )
            else:
                self.providers["local"] = OllamaProvider(gateway_config.ollama_base_url)
        self.providers.setdefault(
            "groq",
            GroqProvider(
                model=gateway_config.groq_model,
                enabled=gateway_config.groq_enabled,
                timeout_seconds=gateway_config.groq_timeout_seconds,
                reasoning_effort=gateway_config.groq_reasoning_effort,
            ),
        )
        self.providers.setdefault(
            "gemini",
            GeminiProvider(
                model=gateway_config.gemini_model,
                enabled=gateway_config.gemini_enabled,
                timeout_seconds=gateway_config.gemini_timeout_seconds,
            ),
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
        if self.config.provider == "hybrid":
            return await self._generate_hybrid(request, route)
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

    async def _generate_hybrid(self, request: LLMRequest, route: ModelRoute) -> LLMResponse:
        decision = self.capability_router.decide(request, route)
        last_error: ModelProviderError | None = None
        for attempt, provider_name in enumerate(decision.providers, start=1):
            provider = self.providers.get(provider_name)
            model = self._hybrid_models[provider_name]
            if provider is None:
                error = ModelProviderError("provider_not_registered")
                last_error = error
                await self._emit_route_event(route, provider_name, model, decision.reason, attempt, "fallback", str(error))
                continue
            if any(message.media for message in request.messages) and provider_name != "gemini":
                error = ModelProviderError("multimodal_provider_unsupported")
                last_error = error
                await self._emit_route_event(route, provider_name, model, decision.reason, attempt, "fallback", str(error))
                continue
            routed = self._request_for_provider(request, model, provider_name)
            await self._emit_route_event(route, provider_name, model, decision.reason, attempt, "selected", None)
            try:
                response = await provider.generate(routed)
            except ModelProviderError as exc:
                last_error = exc
                LOGGER.warning(
                    "model route failed provider=%s model=%s route=%s reason=%s error=%s",
                    provider_name,
                    model,
                    route.value,
                    decision.reason,
                    str(exc)[:120],
                )
                if attempt < len(decision.providers) and self._should_fallback(str(exc)):
                    await self._emit_route_event(route, provider_name, model, decision.reason, attempt, "fallback", str(exc))
                    continue
                raise
            LOGGER.info(
                "model route completed provider=%s model=%s route=%s reason=%s attempt=%d",
                provider_name,
                response.model or model,
                route.value,
                decision.reason,
                attempt,
            )
            if response.provider is None:
                return replace(response, provider=provider_name)
            return response
        if last_error is not None:
            raise last_error
        raise ModelProviderError("no_model_route_available")

    @staticmethod
    def _should_fallback(error_code: str) -> bool:
        non_retryable = (
            "_tool_schema_invalid",
            "_tool_call_invalid",
            "_media_invalid",
            "_system_media_unsupported",
            "_multimodal_unsupported",
        )
        return not error_code.endswith(non_retryable)

    @classmethod
    def _request_for_provider(cls, request: LLMRequest, model: str, provider: str) -> LLMRequest:
        if provider not in {"groq", "gemini", "openai"}:
            return replace(request, model=model)
        return replace(request, model=model, messages=cls._compact_cloud_messages(request.messages))

    @staticmethod
    def _compact_cloud_messages(messages: tuple[LLMMessage, ...]) -> tuple[LLMMessage, ...]:
        """Keep the system contract and recent evidence; avoid full-history cloud calls."""

        if len(messages) <= 8 and sum(len(message.content) for message in messages) <= 24_000:
            return messages
        system = next((message for message in messages if message.role.value == "system"), None)
        tail = list(messages[-7:])
        selected: list[LLMMessage] = []
        if system is not None:
            selected.append(system)
        for message in tail:
            if system is not None and message == system:
                continue
            content = message.content
            if len(content) > 6_000:
                content = content[:5_800] + "\n[history item truncated]"
            selected.append(LLMMessage(message.role, content, message.media))
        return tuple(selected)

    async def health(self, route: ModelRoute = ModelRoute.GENERAL_REASONING) -> ModelHealth:
        selection = self.selection(route)
        provider = self.providers.get(selection.provider)
        if provider is None or not hasattr(provider, "health"):
            return ModelHealth.unavailable(selection.provider, "health_not_supported")
        return await provider.health(selection.model)

    async def _emit_route_event(
        self,
        route: ModelRoute,
        provider: str,
        model: str,
        reason: str,
        attempt: int,
        outcome: str,
        error_code: str | None,
    ) -> None:
        LOGGER.info(
            "model route selected provider=%s model=%s route=%s reason=%s attempt=%d outcome=%s",
            provider,
            model,
            route.value,
            reason,
            attempt,
            outcome,
        )
        if self._repository is None and self._event_bus is None:
            return
        event_type = "model.route.selected" if outcome == "selected" else "model.route.fallback"
        payload: dict[str, object] = {
            "route": route.value,
            "provider": provider,
            "model": model,
            "reason": reason,
            "attempt": attempt,
            "outcome": outcome,
        }
        if error_code:
            payload["error_code"] = error_code[:120]
        event = Event.create(
            event_type,
            EventCategory.MODEL,
            correlation_id=f"model-route-{route.value}",
            payload=payload,
            state=EventState.ACCEPTED,
        )
        if self._repository is not None:
            self._repository.append_event(event)
        if self._event_bus is not None:
            await self._event_bus.publish(event)

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
