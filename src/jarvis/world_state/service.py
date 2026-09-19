"""Durable world state, observation provenance, freshness, and conflicts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from ..bus import InMemoryEventBus
from ..contracts import Observation, WorldStateConflict, WorldStateFact, WorldStateQuery, WorldStateSnapshot
from ..events import Event, EventCategory, EventState
from ..persistence.repositories import RuntimeRepository


class DurableWorldStateService:
    """World state is current evidence, never silently promoted to memory."""

    SOURCE_AUTHORITY = {
        "user": 100,
        "runtime": 80,
        "satellite": 70,
        "git": 65,
        "build": 65,
        "test": 65,
        "network": 55,
        "system": 50,
        "venom": 45,
    }

    def __init__(self, repository: RuntimeRepository, event_bus: InMemoryEventBus) -> None:
        self.repository = repository
        self.event_bus = event_bus

    async def observe(self, observation: Observation, owner_id: str | None = None) -> None:
        if owner_id is not None and observation.owner_id is not None and owner_id != observation.owner_id:
            raise ValueError("world observation owner binding mismatch")
        owner = owner_id or observation.owner_id
        if not owner:
            raise ValueError("world observation requires owner_id")
        if not observation.subject.strip():
            raise ValueError("world observation subject cannot be empty")
        if not 0.0 <= observation.confidence <= 1.0:
            raise ValueError("observation confidence must be between 0 and 1")
        bound_observation = observation if observation.owner_id == owner else replace(observation, owner_id=owner)
        self.repository.insert_world_observation(bound_observation, owner)
        authority = bound_observation.authority_level or self.SOURCE_AUTHORITY.get(bound_observation.source, 0)
        for key, value in self._fact_values(bound_observation):
            await self._fuse(
                WorldStateFact(
                    fact_id=f"fact-{uuid4()}", owner_id=owner, key=key, value=value,
                    source=bound_observation.source, source_reference=bound_observation.source_reference,
                    observed_at=bound_observation.observed_at, freshness=bound_observation.freshness_seconds,
                    expires_at=bound_observation.expires_at, confidence=bound_observation.confidence,
                    authority_level=authority, conflict_state="clear", device_id=bound_observation.device_id,
                    scope=bound_observation.scope,
                )
            )
        await self._emit("world_state.observation", owner, {"observation_id": observation.observation_id, "subject": observation.subject})

    async def set_fact(
        self,
        owner_id: str,
        key: str,
        value: object,
        *,
        source: str = "runtime",
        source_reference: str | None = None,
        confidence: float = 1.0,
        freshness_seconds: float | None = None,
        expires_at: datetime | None = None,
        device_id: str | None = None,
        authority_level: int = 0,
        scope: str = "owner",
    ) -> None:
        now = datetime.now(UTC)
        await self.observe(
            Observation(
                f"observation-{uuid4()}", source, now, key, {"value": value}, confidence,
                owner_id, source_reference, freshness_seconds, expires_at, authority_level,
                "clear", device_id, scope,
            ),
            owner_id,
        )

    async def ingest_event(self, owner_id: str, event: Event) -> None:
        """Map explicit runtime evidence to facts without asking an LLM to guess."""
        payload = dict(event.payload)
        if event.event_type == "run.completed":
            await self.set_fact(owner_id, "runtime.last_run", payload, source="runtime", source_reference=event.event_id, freshness_seconds=3600)
        elif event.event_type in {"model.failed", "tool.failed", "run.failed"}:
            await self.set_fact(owner_id, "runtime.last_failure", {"event_type": event.event_type, **payload}, source="runtime", source_reference=event.event_id, freshness_seconds=7200)
        elif event.event_type.startswith("device."):
            await self.set_fact(owner_id, f"device.{event.event_type}", payload, source="satellite", source_reference=event.event_id, freshness_seconds=300)

    async def facts(self, query: WorldStateQuery) -> tuple[WorldStateFact, ...]:
        rows = self.repository.world_facts(
            query.owner_id,
            query.key_prefix,
            query.include_expired,
            scope=query.scope,
            scopes=query.scopes,
        )
        now = datetime.now(UTC)
        grouped: dict[str, WorldStateFact] = {}
        for row in rows:
            fact = self._fact(row)
            if not query.include_expired:
                if fact.conflict_state == "expired":
                    continue
                if fact.expires_at and fact.expires_at <= now:
                    continue
                if fact.freshness and (fact.observed_at + timedelta(seconds=fact.freshness)) <= now:
                    continue
            current = grouped.get(fact.key)
            if current is None or self._rank(fact) > self._rank(current):
                grouped[fact.key] = fact
        return tuple(sorted(grouped.values(), key=lambda fact: fact.key))

    async def conflicts(self, owner_id: str) -> tuple[WorldStateConflict, ...]:
        return tuple(self._conflict(row) for row in self.repository.world_conflicts(owner_id))

    async def snapshot(self, owner_id: str | None = None) -> WorldStateSnapshot:
        if owner_id is None:
            return WorldStateSnapshot(f"snapshot-{uuid4()}", datetime.now(UTC))
        current = await self.facts(WorldStateQuery(owner_id))
        observations = tuple(self._observation(row) for row in self.repository.world_observations(owner_id, 50))
        conflicts = await self.conflicts(owner_id)
        facts = {fact.key: fact.value for fact in current}
        return WorldStateSnapshot(f"snapshot-{uuid4()}", datetime.now(UTC), observations, facts, conflicts)

    async def expire(self, owner_id: str) -> int:
        now = datetime.now(UTC)
        expired = 0
        for row in self.repository.world_facts(owner_id, include_expired=True):
            is_expired = False
            if row["expires_at"] and datetime.fromisoformat(row["expires_at"]) <= now:
                is_expired = True
            elif row.get("freshness") and (datetime.fromisoformat(row["observed_at"]) + timedelta(seconds=float(row["freshness"]))) <= now:
                is_expired = True
            if is_expired and row["conflict_state"] != "expired":
                self.repository.update_world_fact(row["id"], conflict_state="expired")
                expired += 1
                await self._emit("world_state.expired", owner_id, {"fact_id": row["id"], "key": row["key"]}, EventState.COMPLETED)
        return expired

    @staticmethod
    def _fact_values(observation: Observation) -> tuple[tuple[str, object], ...]:
        if not observation.value:
            return ((observation.subject, {}),)
        if set(observation.value) == {"value"}:
            return ((observation.subject, observation.value["value"]),)
        return tuple((f"{observation.subject}.{key}", value) for key, value in observation.value.items())

    async def _fuse(self, fact: WorldStateFact) -> None:
        existing = self.repository.world_facts(fact.owner_id, fact.key, include_expired=True)
        current = [row for row in existing if row["key"] == fact.key and row["conflict_state"] != "expired"]
        previous = max((self._fact(row) for row in current), key=self._rank, default=None)
        if previous and previous.value == fact.value:
            self.repository.update_world_fact(previous.fact_id, observed_at=fact.observed_at, freshness=fact.freshness, expires_at=fact.expires_at, confidence=fact.confidence, source_reference=fact.source_reference)
            return
        if previous and previous.value != fact.value:
            self.repository.update_world_fact(previous.fact_id, conflict_state="conflicted")
            fact = WorldStateFact(
                fact.fact_id, fact.owner_id, fact.key, fact.value, fact.source, fact.source_reference,
                fact.observed_at, fact.freshness, fact.expires_at, fact.confidence, fact.authority_level,
                "conflicted", fact.device_id, fact.scope,
            )
        self.repository.insert_world_fact(fact)
        if previous and previous.value != fact.value:
            conflict = WorldStateConflict(
                f"conflict-{uuid4()}", fact.owner_id, fact.key, (previous.fact_id, fact.fact_id),
                "competing observations", datetime.now(UTC), False,
            )
            self.repository.insert_world_conflict(conflict)
            await self._emit("world_state.conflict", fact.owner_id, {"key": fact.key, "fact_ids": list(conflict.fact_ids)})
        await self._emit("world_state.updated", fact.owner_id, {"key": fact.key, "fact_id": fact.fact_id}, EventState.COMPLETED)

    @classmethod
    def _rank(cls, fact: WorldStateFact) -> tuple[int, float, datetime]:
        return (fact.authority_level or cls.SOURCE_AUTHORITY.get(fact.source, 0), fact.confidence, fact.observed_at)

    @staticmethod
    def _fact(row: Mapping[str, object]) -> WorldStateFact:
        return WorldStateFact(
            row["id"], row["owner_id"], row["key"], json.loads(row["value_json"]), row["source"], row["source_reference"],
            datetime.fromisoformat(row["observed_at"]), row["freshness"], datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None,
            row["confidence"], row["authority_level"], row["conflict_state"], row["device_id"], row["scope"],
        )

    @staticmethod
    def _observation(row: Mapping[str, object]) -> Observation:
        return Observation(
            row["id"], row["source"], datetime.fromisoformat(row["observed_at"]), row["subject"], json.loads(row["value_json"]), row["confidence"],
            row["owner_id"], row["source_reference"], row["freshness_seconds"], datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None,
            row["authority_level"], row["conflict_state"], row["device_id"], row["scope"],
        )

    @staticmethod
    def _conflict(row: Mapping[str, object]) -> WorldStateConflict:
        return WorldStateConflict(row["id"], row["owner_id"], row["key"], tuple(json.loads(row["fact_ids_json"])), row["reason"], datetime.fromisoformat(row["detected_at"]), bool(row["resolved"]))

    async def _emit(self, event_type: str, owner_id: str, payload: dict[str, object], state: EventState = EventState.EMITTED) -> None:
        event = Event.create(event_type, EventCategory.WORLD_STATE, correlation_id=f"world-{owner_id}", actor_id=owner_id, payload=payload, state=state)
        self.repository.append_event(event)
        await self.event_bus.publish(event)
