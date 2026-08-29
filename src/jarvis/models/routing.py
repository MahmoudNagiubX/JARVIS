"""Inspectable model route categories."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


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


def default_selections(provider: str, primary_model: str, fallback_model: str) -> dict[ModelRoute, ModelSelection]:
    return {
        route: ModelSelection(route, provider, primary_model)
        for route in ModelRoute
    } | {
        ModelRoute.CODING_WORKER: ModelSelection(ModelRoute.CODING_WORKER, provider, fallback_model),
    }
