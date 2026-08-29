"""Memory persistence contracts, independent of storage technology."""

from __future__ import annotations

from collections.abc import Awaitable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    memory_id: str
    owner_id: str
    content: str
    created_at: datetime
    kind: str = "semantic"
    metadata: Mapping[str, object] = field(default_factory=dict)


class MemoryStore(Protocol):
    def save(self, record: MemoryRecord) -> Awaitable[None]: ...

    def recall(self, owner_id: str, query: str, limit: int = 10) -> Awaitable[tuple[MemoryRecord, ...]]: ...
