"""Explicit local-model capability probes.

Probes are opt-in operations. Importing or bootstrapping JARVIS never contacts
Ollama and never downloads a model.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from ..contracts import LLMMessage, LLMRequest, LLMRole
from .gateway import ModelGateway
from .routing import ModelRoute


@dataclass(frozen=True, slots=True)
class ModelCapabilityProbe:
    provider: str
    model: str
    available: bool
    checked_at: datetime
    health_reason: str
    capabilities: tuple[str, ...] = ()
    generation_checked: bool = False
    latency_ms: float | None = None
    failure: str | None = None

    def as_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["checked_at"] = self.checked_at.isoformat()
        return value


class LocalModelCapabilityProbe:
    """Check an already configured model without changing local state."""

    def __init__(self, gateway: ModelGateway) -> None:
        self.gateway = gateway

    async def run(
        self,
        route: ModelRoute = ModelRoute.FAST_CONVERSATION,
        *,
        exercise_generation: bool = False,
        timeout_seconds: float = 10.0,
    ) -> ModelCapabilityProbe:
        if timeout_seconds <= 0 or timeout_seconds > 60:
            raise ValueError("model probe timeout must be between 0 and 60 seconds")
        selection = self.gateway.selection(route)
        health = await self.gateway.health(route)
        checked_at = datetime.now(UTC)
        capabilities = ("health",) if health.available else ()
        if not health.available or not exercise_generation:
            return ModelCapabilityProbe(
                health.provider, selection.model, health.available, checked_at,
                health.reason, capabilities, False,
            )
        started = time.perf_counter()
        try:
            response = await asyncio.wait_for(
                self.gateway.generate(
                    LLMRequest(
                        "model-capability-probe",
                        (LLMMessage(LLMRole.USER, "Reply with the single word ready."),),
                        model=selection.model, max_output_tokens=16,
                        timeout_seconds=timeout_seconds,
                    ), route,
                ), timeout=timeout_seconds,
            )
        except Exception as exc:
            return ModelCapabilityProbe(
                health.provider, selection.model, False, checked_at, health.reason,
                capabilities, True, (time.perf_counter() - started) * 1000,
                f"{exc.__class__.__name__}",
            )
        capabilities = (*capabilities, "chat")
        if response.tool_calls:
            capabilities = (*capabilities, "tool_calls")
        return ModelCapabilityProbe(
            health.provider, response.model, True, checked_at, health.reason,
            capabilities, True, (time.perf_counter() - started) * 1000,
        )
