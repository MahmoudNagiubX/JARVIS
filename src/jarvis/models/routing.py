"""Inspectable model route categories."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from ..contracts import LLMRequest


class ModelRoute(StrEnum):
    FAST_CONVERSATION = "fast_conversation"
    GENERAL_REASONING = "general_reasoning"
    TOOL_ORCHESTRATION = "tool_orchestration"
    VISION = "vision"
    CODING_WORKER = "coding_worker"


@dataclass(frozen=True, slots=True)
class ModelSelection:
    route: ModelRoute
    provider: str
    model: str


@dataclass(frozen=True, slots=True)
class CapabilityRouteDecision:
    """Deterministic provider order for one request."""

    providers: tuple[str, ...]
    reason: str


class CapabilityRouter:
    """Choose a capability route without spending an LLM call."""

    _VISION_MARKERS = (
        "screenshot", "screen shot", "screen", "image", "photo", "picture",
        "visual", "vision", "document", "pdf", "scan", "look at",
    )
    _COMPLEX_MARKERS = (
        "plan", "planning", "reason", "reasoning", "analyze", "analysis",
        "code", "coding", "implement", "debug", "research", "multi-step",
        "workflow", "compare", "summarize", "explain", "design",
    )
    _SIMPLE_MARKERS = (
        "open", "launch", "start", "close", "volume", "mute", "unmute",
        "timer", "alarm", "minimize", "maximize", "restore", "status",
    )

    def decide(self, request: LLMRequest, route: ModelRoute) -> CapabilityRouteDecision:
        # Capability markers describe the owner's request, not the system
        # contract.  System prompts commonly contain words such as
        # ``explain`` or ``research`` as constraints, which must not promote a
        # simple local turn to a cloud route.
        text = " ".join(
            message.content
            for message in request.messages[-3:]
            if message.role.value != "system"
        ).casefold()
        context_chars = sum(len(message.content) for message in request.messages)
        has_media = any(message.media for message in request.messages)
        if has_media or route is ModelRoute.VISION or self._contains_marker(text, self._VISION_MARKERS):
            # Media must not be sent to a text-only fallback. Text-only visual
            # prompts may still use the local model if Gemini is unavailable.
            fallback = ("local",) if not has_media else ()
            return CapabilityRouteDecision(("gemini", *fallback), "multimodal_or_visual_capability")
        if context_chars > 16_000 or len(request.messages) > 10:
            return CapabilityRouteDecision(("gemini", "groq", "local"), "large_context")
        if route is ModelRoute.TOOL_ORCHESTRATION and self._contains_marker(text, self._SIMPLE_MARKERS) and not self._contains_marker(text, self._COMPLEX_MARKERS):
            return CapabilityRouteDecision(("local", "groq", "gemini"), "simple_command_capability")
        if route in {ModelRoute.GENERAL_REASONING, ModelRoute.TOOL_ORCHESTRATION, ModelRoute.CODING_WORKER}:
            return CapabilityRouteDecision(("groq", "gemini", "local"), "reasoning_or_tool_capability")
        if request.tools or self._contains_marker(text, self._COMPLEX_MARKERS):
            return CapabilityRouteDecision(("groq", "gemini", "local"), "complex_intent_or_declared_tools")
        return CapabilityRouteDecision(("local", "groq", "gemini"), "fast_local_capability")

    @staticmethod
    def _contains_marker(text: str, markers: tuple[str, ...]) -> bool:
        return any(marker in text for marker in markers)


def hybrid_selections(local_model: str, groq_model: str, gemini_model: str) -> dict[ModelRoute, ModelSelection]:
    """Expose the deterministic primary plan to health/UI callers."""

    return {
        ModelRoute.FAST_CONVERSATION: ModelSelection(ModelRoute.FAST_CONVERSATION, "local", local_model),
        ModelRoute.GENERAL_REASONING: ModelSelection(ModelRoute.GENERAL_REASONING, "groq", groq_model),
        ModelRoute.TOOL_ORCHESTRATION: ModelSelection(ModelRoute.TOOL_ORCHESTRATION, "groq", groq_model),
        ModelRoute.VISION: ModelSelection(ModelRoute.VISION, "gemini", gemini_model),
        ModelRoute.CODING_WORKER: ModelSelection(ModelRoute.CODING_WORKER, "groq", groq_model),
    }


def default_selections(provider: str, primary_model: str, fallback_model: str) -> dict[ModelRoute, ModelSelection]:
    return {
        route: ModelSelection(route, provider, primary_model)
        for route in ModelRoute
    } | {
        ModelRoute.CODING_WORKER: ModelSelection(ModelRoute.CODING_WORKER, provider, fallback_model),
    }
