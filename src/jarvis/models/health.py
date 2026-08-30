"""Small health snapshot for model adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class ModelHealth:
    provider: str
    available: bool
    checked_at: datetime
    reason: str
    model: str | None = None
    latency_ms: float | None = None

    @classmethod
    def unavailable(cls, provider: str, reason: str) -> "ModelHealth":
        return cls(provider, False, datetime.now(UTC), reason)
