"""Durable, auditable memory with deterministic candidate extraction."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import uuid4

from ..authority.audit.service import DurableAuditService
from ..bus import InMemoryEventBus
from ..contracts import (
    AuditRecord,
    MemoryCandidate,
    MemoryQuery,
    MemoryRecord,
    MemoryRetention,
    MemorySensitivity,
    MemorySource,
)
from ..events import Event, EventCategory, EventState
from ..persistence.repositories import RuntimeRepository
from .policy import MemoryPolicy
from .retrieval import EmbeddingProvider, KeywordMemoryRetriever


class DurableMemoryService:
    """Product-owned memory authority; retrieval backends remain replaceable."""

    def __init__(
        self,
        repository: RuntimeRepository,
        event_bus: InMemoryEventBus,
        audit: DurableAuditService | None = None,
        policy: MemoryPolicy | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.audit = audit
        self.policy = policy or MemoryPolicy()
        self.embedding_provider = embedding_provider

    async def create(self, candidate: MemoryCandidate) -> MemoryRecord | None:
        decision = self.policy.evaluate(candidate)
        if not decision.allowed:
            await self._emit("memory.candidate", candidate.owner_id, {"accepted": False, "reason": decision.reason})
            return None
        candidate = MemoryCandidate(
            candidate.owner_id,
            decision.normalized_content,
            candidate.category,
            candidate.source,
            candidate.source_reference,
            dict(candidate.structured_data),
            candidate.confidence,
            candidate.sensitivity,
            tuple(sorted(set(candidate.tags))),
        )
        await self._emit("memory.candidate", candidate.owner_id, {"accepted": True, "category": candidate.category})
        existing = self._find_duplicate(candidate)
        if existing is not None:
            self.repository.update_memory(
                candidate.owner_id,
                existing.memory_id,
                last_accessed_at=datetime.now(UTC),
            )
            return existing
        previous = self._find_conflict(candidate)
        now = datetime.now(UTC)
        record = MemoryRecord(
            memory_id=f"memory-{uuid4()}",
            owner_id=candidate.owner_id,
            content=candidate.content,
            created_at=now,
            kind="semantic",
            metadata={"provenance": candidate.source_reference},
            category=candidate.category,
            structured_data=candidate.structured_data,
            source=candidate.source,
            source_reference=candidate.source_reference,
            updated_at=now,
            confidence=float(candidate.confidence),
            sensitivity=candidate.sensitivity,
            retention_policy=MemoryRetention.PERMANENT.value,
            supersedes=previous.memory_id if previous else None,
            tags=candidate.tags,
        )
        self.repository.insert_memory(record)
        if previous is not None:
            self.repository.update_memory(candidate.owner_id, previous.memory_id, status="superseded", updated_at=now)
            await self._emit(
                "memory.conflict",
                candidate.owner_id,
                {"memory_id": record.memory_id, "previous_id": previous.memory_id, "category": candidate.category},
            )
            await self._emit("memory.superseded", candidate.owner_id, {"memory_id": previous.memory_id, "by": record.memory_id})
        await self._audit(candidate.owner_id, "memory.created", "created", {"memory_id": record.memory_id, "category": record.category})
        await self._emit("memory.created", candidate.owner_id, {"memory_id": record.memory_id, "category": record.category}, EventState.COMPLETED)
        return record

    async def save(self, record: MemoryRecord) -> None:
        candidate = MemoryCandidate(
            record.owner_id,
            record.content,
            record.category,
            record.source,
            record.source_reference,
            record.structured_data,
            record.confidence,
            record.sensitivity,
            record.tags,
        )
        decision = self.policy.evaluate(candidate)
        if not decision.allowed:
            raise ValueError(decision.reason)
        self.repository.insert_memory(record)
        await self._emit("memory.created", record.owner_id, {"memory_id": record.memory_id, "category": record.category}, EventState.COMPLETED)

    async def recall(self, owner_id: str, query: str, limit: int = 10) -> tuple[MemoryRecord, ...]:
        return await self.search(MemoryQuery(owner_id=owner_id, text=query, limit=limit))

    async def search(self, query: MemoryQuery) -> tuple[MemoryRecord, ...]:
        rows = self.repository.memories(
            query.owner_id,
            query.statuses,
            query.include_archived,
            query.category,
            query.source,
            query.tags,
        )
        records = tuple(self._record(row) for row in rows)
        return KeywordMemoryRetriever.rank(records, query)

    async def get(self, owner_id: str, memory_id: str) -> MemoryRecord | None:
        row = self.repository.memory(owner_id, memory_id)
        return self._record(row) if row else None

    async def update(
        self,
        owner_id: str,
        memory_id: str,
        *,
        content: str | None = None,
        category: str | None = None,
        structured_data: Mapping[str, object] | None = None,
        tags: tuple[str, ...] | None = None,
        sensitivity: str | None = None,
    ) -> MemoryRecord:
        current = await self.get(owner_id, memory_id)
        if current is None:
            raise KeyError(memory_id)
        candidate = MemoryCandidate(
            owner_id,
            content if content is not None else current.content,
            category if category is not None else current.category,
            current.source,
            current.source_reference,
            structured_data if structured_data is not None else current.structured_data,
            current.confidence,
            sensitivity if sensitivity is not None else current.sensitivity,
            tags if tags is not None else current.tags,
        )
        decision = self.policy.evaluate(candidate)
        if not decision.allowed:
            raise ValueError(decision.reason)
        row = self.repository.update_memory(
            owner_id,
            memory_id,
            content=decision.normalized_content,
            category=candidate.category,
            structured_data_json=json.dumps(dict(candidate.structured_data), sort_keys=True, ensure_ascii=False, separators=(",", ":")),
            sensitivity=candidate.sensitivity,
            tags_json=json.dumps(list(candidate.tags), ensure_ascii=False),
            updated_at=datetime.now(UTC),
        )
        await self._audit(owner_id, "memory.updated", "updated", {"memory_id": memory_id})
        await self._emit("memory.updated", owner_id, {"memory_id": memory_id}, EventState.COMPLETED)
        return self._record(row)

    async def correct(self, owner_id: str, memory_id: str, content: str) -> MemoryRecord:
        return await self.update(owner_id, memory_id, content=content)

    async def delete(self, owner_id: str, memory_id: str) -> None:
        if await self.get(owner_id, memory_id) is None:
            raise KeyError(memory_id)
        self.repository.update_memory(owner_id, memory_id, status="deleted", archived=1, updated_at=datetime.now(UTC))
        await self._audit(owner_id, "memory.deleted", "deleted", {"memory_id": memory_id})
        await self._emit("memory.deleted", owner_id, {"memory_id": memory_id}, EventState.COMPLETED)

    async def forget_category(self, owner_id: str, category: str) -> int:
        records = await self.search(MemoryQuery(owner_id, category=category, statuses=("active",), limit=100))
        for record in records:
            await self.delete(owner_id, record.memory_id)
        return len(records)

    async def pin(self, owner_id: str, memory_id: str, pinned: bool = True) -> MemoryRecord:
        row = self.repository.update_memory(owner_id, memory_id, pinned=int(pinned), updated_at=datetime.now(UTC))
        await self._audit(owner_id, "memory.updated", "pinned", {"memory_id": memory_id, "pinned": pinned})
        await self._emit("memory.updated", owner_id, {"memory_id": memory_id, "pinned": pinned}, EventState.COMPLETED)
        return self._record(row)

    async def archive(self, owner_id: str, memory_id: str, archived: bool = True) -> MemoryRecord:
        row = self.repository.update_memory(owner_id, memory_id, archived=int(archived), updated_at=datetime.now(UTC))
        await self._audit(owner_id, "memory.updated", "archived", {"memory_id": memory_id, "archived": archived})
        await self._emit("memory.updated", owner_id, {"memory_id": memory_id, "archived": archived}, EventState.COMPLETED)
        return self._record(row)

    async def remember_from_conversation(self, owner_id: str, text: str, source_reference: str | None = None) -> tuple[MemoryRecord, ...]:
        records: list[MemoryRecord] = []
        for candidate in self.extract_candidates(owner_id, text, source_reference):
            record = await self.create(candidate)
            if record is not None:
                records.append(record)
        return tuple(records)

    @staticmethod
    def extract_candidates(owner_id: str, text: str, source_reference: str | None = None) -> tuple[MemoryCandidate, ...]:
        normalized = " ".join(text.split())
        lowered = normalized.casefold()
        if len(normalized) < 5 or lowered in {"hello", "hi", "thanks", "thank you", "ok", "okay"}:
            return ()
        source = MemorySource.CONVERSATION.value
        candidates: list[MemoryCandidate] = []
        if re.search(r"keep (your|the) answers? short|be concise|short answers", lowered):
            candidates.append(MemoryCandidate(owner_id, "Mahmoud prefers concise answers.", "preference", source, source_reference, {"key": "verbosity", "value": "concise"}, 0.98, tags=("style",)))
        match = re.search(r"(?:call me|my name is) ([A-Za-z][\w -]{1,50})", normalized, re.I)
        if match:
            name = match.group(1).strip(" .,!?")
            candidates.append(MemoryCandidate(owner_id, f"Preferred name is {name}.", "profile", source, source_reference, {"key": "preferred_name", "value": name}, 0.98, tags=("identity",)))
        if re.search(r"\b(i prefer|i like|my preference is)\b", lowered):
            candidates.append(MemoryCandidate(owner_id, normalized, "preference", source, source_reference, {"key": "freeform_preference", "value": normalized}, 0.85))
        match = re.search(r"(?:working on|project is|project:)\s*([^.!?]{2,100})", normalized, re.I)
        if match:
            project = match.group(1).strip()
            candidates.append(MemoryCandidate(owner_id, f"Mahmoud is working on {project}.", "project", source, source_reference, {"key": "active_project", "value": project}, 0.88, tags=("work",)))
        if re.search(r"\bdeadline\b|\bdue\b", lowered):
            candidates.append(MemoryCandidate(owner_id, normalized, "task", source, source_reference, {"key": "deadline_context", "value": normalized}, 0.82, tags=("deadline",)))
        if lowered.startswith("remember that") or lowered.startswith("important:"):
            candidates.append(MemoryCandidate(owner_id, normalized, "fact", source, source_reference, {}, 0.82))
        if lowered.startswith("decision:"):
            candidates.append(MemoryCandidate(owner_id, normalized, "decision", source, source_reference, {}, 0.9))
        if lowered.startswith("goal:"):
            candidates.append(MemoryCandidate(owner_id, normalized, "goal", source, source_reference, {}, 0.88))
        return tuple(candidates)

    async def maintain(self, owner_id: str) -> dict[str, int]:
        now = datetime.now(UTC)
        expired = 0
        archived = 0
        for record in await self.search(MemoryQuery(owner_id, statuses=("active",), include_archived=True, limit=100)):
            if record.valid_until and record.valid_until <= now:
                self.repository.update_memory(owner_id, record.memory_id, status="expired", updated_at=now)
                expired += 1
            elif record.retention_policy == MemoryRetention.TEMPORARY.value and not record.pinned:
                self.repository.update_memory(owner_id, record.memory_id, archived=1, updated_at=now)
                archived += 1
        return {"expired": expired, "archived": archived}

    def _find_duplicate(self, candidate: MemoryCandidate) -> MemoryRecord | None:
        for record in self._records(candidate.owner_id, ("active",)):
            if record.content.casefold() == candidate.content.casefold():
                return record
            key = candidate.structured_data.get("key")
            if key and record.category == candidate.category and record.structured_data.get("key") == key and record.structured_data.get("value") == candidate.structured_data.get("value"):
                return record
        return None

    def _find_conflict(self, candidate: MemoryCandidate) -> MemoryRecord | None:
        key = candidate.structured_data.get("key")
        if not key:
            return None
        for record in self._records(candidate.owner_id, ("active",)):
            if record.category == candidate.category and record.structured_data.get("key") == key and record.content.casefold() != candidate.content.casefold():
                return record
        return None

    def _records(self, owner_id: str, statuses: tuple[str, ...]) -> tuple[MemoryRecord, ...]:
        return tuple(self._record(row) for row in self.repository.memories(owner_id, statuses, True))

    @staticmethod
    def _record(row: Mapping[str, object] | None) -> MemoryRecord:
        if row is None:
            raise KeyError("memory")
        return MemoryRecord(
            row["id"], row["owner_id"], row["content"], datetime.fromisoformat(row["created_at"]),
            "semantic", json.loads(row["metadata_json"]), row["category"], json.loads(row["structured_data_json"]),
            row["source"], row["source_reference"], datetime.fromisoformat(row["updated_at"]),
            datetime.fromisoformat(row["last_accessed_at"]) if row["last_accessed_at"] else None,
            row["confidence"], row["sensitivity"], row["scope"],
            datetime.fromisoformat(row["valid_from"]) if row["valid_from"] else None,
            datetime.fromisoformat(row["valid_until"]) if row["valid_until"] else None,
            row["retention_policy"], row["status"], row["supersedes"], tuple(json.loads(row["tags_json"])),
            bool(row["pinned"]), bool(row["archived"]), tuple(json.loads(row["embedding_json"])) if row["embedding_json"] else None,
        )

    async def _audit(self, owner_id: str, event_type: str, outcome: str, metadata: dict[str, object]) -> None:
        if self.audit is None:
            return
        await self.audit.record(AuditRecord(f"audit-{uuid4()}", event_type, datetime.now(UTC), owner_id, None, f"memory-{owner_id}", outcome, None, metadata))

    async def _emit(self, event_type: str, owner_id: str, payload: dict[str, object], state: EventState = EventState.EMITTED) -> None:
        event = Event.create(event_type, EventCategory.MEMORY, correlation_id=f"memory-{owner_id}", actor_id=owner_id, payload=payload, state=state)
        self.repository.append_event(event)
        await self.event_bus.publish(event)
