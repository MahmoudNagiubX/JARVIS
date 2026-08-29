"""Append-oriented audit contracts."""

from __future__ import annotations

from collections.abc import Awaitable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class AuditRecord:
    record_id: str
    event_type: str
    occurred_at: datetime
    actor_id: str | None
    device_id: str | None
    correlation_id: str
    outcome: str
    reason_code: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)


class AuditService(Protocol):
    def record(self, record: AuditRecord) -> Awaitable[None]: ...

    def query(self, correlation_id: str | None = None) -> Awaitable[tuple[AuditRecord, ...]]: ...
