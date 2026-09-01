"""Memory persistence contracts, independent of storage technology."""

from __future__ import annotations

from collections.abc import Awaitable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol


class MemorySource(StrEnum):
    CONVERSATION = "conversation"
    USER = "user"
    EVENT = "event"
    IMPORT = "import"
    SYSTEM = "system"


class MemorySensitivity(StrEnum):
    PUBLIC = "public"
    PERSONAL = "personal"
    SENSITIVE = "sensitive"
    SECRET = "secret"


class MemoryRetention(StrEnum):
    PERMANENT = "permanent"
    UNTIL_REVIEW = "until_review"
    TEMPORARY = "temporary"
    EXPIRES = "expires"


class MemoryConfidence(float):
    """A bounded confidence value suitable for policy and ranking."""

    def __new__(cls, value: float) -> "MemoryConfidence":
        bounded = float(value)
        if not 0.0 <= bounded <= 1.0:
            raise ValueError("memory confidence must be between 0 and 1")
        return float.__new__(cls, bounded)


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    memory_id: str
    owner_id: str
    content: str
    created_at: datetime
    kind: str = "semantic"
    metadata: Mapping[str, object] = field(default_factory=dict)
    category: str = "fact"
    structured_data: Mapping[str, object] = field(default_factory=dict)
    source: str = MemorySource.CONVERSATION.value
    source_reference: str | None = None
    updated_at: datetime | None = None
    last_accessed_at: datetime | None = None
    confidence: float = 1.0
    sensitivity: str = MemorySensitivity.PERSONAL.value
    scope: str = "owner"
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    retention_policy: str = MemoryRetention.PERMANENT.value
    status: str = "active"
    supersedes: str | None = None
    tags: tuple[str, ...] = ()
    pinned: bool = False
    archived: bool = False
    embedding: tuple[float, ...] | None = None


@dataclass(frozen=True, slots=True)
class MemoryQuery:
    owner_id: str
    text: str = ""
    category: str | None = None
    source: str | None = None
    tags: tuple[str, ...] = ()
    statuses: tuple[str, ...] = ("active",)
    include_archived: bool = False
    limit: int = 10
    scope: str | None = None
    scopes: tuple[str, ...] = ()
    max_item_bytes: int = 2048
    max_total_bytes: int = 8192


@dataclass(frozen=True, slots=True)
class MemoryCandidate:
    owner_id: str
    content: str
    category: str
    source: str = MemorySource.CONVERSATION.value
    source_reference: str | None = None
    structured_data: Mapping[str, object] = field(default_factory=dict)
    confidence: float = 0.8
    sensitivity: str = MemorySensitivity.PERSONAL.value
    tags: tuple[str, ...] = ()
    scope: str = "owner"


class MemoryStore(Protocol):
    def save(self, record: MemoryRecord) -> Awaitable[None]: ...

    def recall(self, owner_id: str, query: str, limit: int = 10) -> Awaitable[tuple[MemoryRecord, ...]]: ...


class MemoryService(MemoryStore, Protocol):
    def create(self, candidate: MemoryCandidate) -> Awaitable[MemoryRecord | None]: ...

    def search(self, query: MemoryQuery) -> Awaitable[tuple[MemoryRecord, ...]]: ...

    def get(self, owner_id: str, memory_id: str) -> Awaitable[MemoryRecord | None]: ...
