"""Low-cardinality metrics derived from the normalized event stream."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any

from ..bus import InMemoryEventBus
from ..events import Event


class ObservabilityService:
    def __init__(self, event_bus: InMemoryEventBus) -> None:
        self._event_bus = event_bus
        self._events = 0
        self._by_category: Counter[str] = Counter()
        self._by_type: Counter[str] = Counter()
        self._failures = 0
        self._last_event_at: datetime | None = None
        self._latencies: Counter[str] = Counter()
        self._tool_call_responses = 0
        self._subscription = event_bus.subscribe("*", self.on_event)

    async def on_event(self, event: Event) -> None:
        self._events += 1
        self._by_category[event.category.value] += 1
        self._by_type[event.event_type] += 1
        if event.state.value == "failed" or event.severity.value in {"error", "critical"}:
            self._failures += 1
        if event.event_type == "model.completed":
            tool_call_count = event.payload.get("tool_call_count")
            if isinstance(tool_call_count, int):
                self._tool_call_responses += max(0, tool_call_count)
        self._last_event_at = event.timestamp
        for key in ("latency_ms", "model_duration_ms", "tool_duration_ms", "worker_duration_ms"):
            value = event.payload.get(key)
            if isinstance(value, (int, float)):
                self._latencies[key] += int(value)

    def snapshot(self) -> dict[str, Any]:
        return {
            "events_total": self._events,
            "events_by_category": dict(self._by_category),
            "events_by_type": dict(self._by_type),
            "failures_total": self._failures,
            "latency_totals_ms": dict(self._latencies),
            "model_requests": self._by_type.get("model.requested", 0),
            "model_failures": self._by_type.get("model.failed", 0),
            "generation_latency_ms": self._latencies.get("latency_ms", 0),
            "tool_call_responses": self._tool_call_responses,
            "runtime_restarts": self._by_type.get("model.runtime.restarted", 0),
            "runtime_ready_latency_ms": self._latencies.get("runtime_ready_latency_ms", 0),
            "last_event_at": self._last_event_at.isoformat() if self._last_event_at else None,
            "storage": "local-process",
            "secrets_retained": False,
        }

    def close(self) -> None:
        if self._subscription is not None:
            self._event_bus.unsubscribe(self._subscription)
            self._subscription = None
