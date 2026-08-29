"""Inspectable request classification; it does not execute capabilities."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ...models.routing import ModelRoute


class RequestRoute(StrEnum):
    DIRECT = "direct"
    TOOL = "tool"
    WORKER = "worker"


@dataclass(frozen=True, slots=True)
class ClassifiedRequest:
    route: RequestRoute
    model_route: ModelRoute
    reason: str


class RequestRouter:
    def classify(self, text: str) -> ClassifiedRequest:
        lowered = text.casefold()
        if any(token in lowered for token in ("research", "investigate", "code", "implement")):
            return ClassifiedRequest(RequestRoute.WORKER, ModelRoute.CODING_WORKER, "worker_keyword")
        if any(token in lowered for token in ("tool", "status", "echo", "computer", "open")):
            return ClassifiedRequest(RequestRoute.TOOL, ModelRoute.TOOL_ORCHESTRATION, "capability_keyword")
        return ClassifiedRequest(RequestRoute.DIRECT, ModelRoute.FAST_CONVERSATION, "default_conversation")
