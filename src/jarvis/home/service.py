"""Contextual home projection and bounded routines over HomeActionService."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Mapping
from uuid import uuid4

from ..bus import InMemoryEventBus
from ..contracts import DeviceIdentity, HomeAction, HomeEntity, HomeResult, Identity
from ..devices.home.service import HomeActionService
from ..events import Event, EventCategory, EventState
from ..persistence.repositories import RuntimeRepository
from ..world_state.service import DurableWorldStateService


@dataclass(frozen=True, slots=True)
class HomeContextSnapshot:
    owner_id: str
    available: bool
    transport: str | None
    updated_at: datetime
    entities: tuple[dict[str, object], ...] = ()
    error: str | None = None


@dataclass(frozen=True, slots=True)
class HomeRoutine:
    routine_id: str
    name: str
    description: str
    actions: tuple[dict[str, object], ...]
    safe: bool = True


@dataclass(frozen=True, slots=True)
class RoutineRun:
    run_id: str
    owner_id: str
    routine_id: str
    status: str
    result: dict[str, object]
    started_at: datetime
    completed_at: datetime | None = None


class HomeContextService:
    """Projects configured Home Assistant state into transient World State."""

    SAFE_ATTRIBUTES = frozenset({"brightness", "temperature", "unit_of_measurement", "friendly_name", "color", "room_id"})

    def __init__(self, home: HomeActionService, world_state: DurableWorldStateService, repository: RuntimeRepository, event_bus: InMemoryEventBus, *, configured_entities: tuple[str, ...] = ()) -> None:
        self.home = home
        self.world_state = world_state
        self.repository = repository
        self.event_bus = event_bus
        self.configured_entities = frozenset(configured_entities)
        self._last: dict[str, HomeContextSnapshot] = {}

    async def refresh(self, identity: Identity, device: DeviceIdentity) -> HomeContextSnapshot:
        now = datetime.now(UTC)
        try:
            entities = await self.home.list_entities(identity, device)
        except Exception as exc:
            return await self._unavailable(identity.owner_id, exc.__class__.__name__)
        if self.home.transport is None:
            return await self._unavailable(identity.owner_id, "home_service_unavailable")
        projected = []
        for entity in entities:
            if self.configured_entities and entity.entity_id not in self.configured_entities:
                continue
            if entity.domain == "person" and entity.entity_id not in self.configured_entities:
                continue
            attributes = {key: value for key, value in entity.attributes.items() if key in self.SAFE_ATTRIBUTES and isinstance(value, (str, int, float, bool))}
            value = {"entity_id": entity.entity_id, "name": entity.name, "domain": entity.domain, "state": entity.state, "room_id": entity.room_id, "attributes": attributes}
            projected.append(value)
            await self.world_state.set_fact(identity.owner_id, f"home.entity.{entity.entity_id}", value, source="home", source_reference=getattr(self.home.transport, "name", "home"), expires_at=now + timedelta(seconds=300), freshness_seconds=300, device_id=device.device_id)
        snapshot = HomeContextSnapshot(identity.owner_id, True, getattr(self.home.transport, "name", None), now, tuple(projected))
        self._last[identity.owner_id] = snapshot
        await self._emit("home.context_updated", identity.owner_id, {"transport": snapshot.transport, "entity_count": len(projected)}, EventState.COMPLETED)
        return snapshot

    async def snapshot(self, owner_id: str) -> HomeContextSnapshot:
        return self._last.get(owner_id, HomeContextSnapshot(owner_id, self.home.transport is not None, getattr(self.home.transport, "name", None), datetime.now(UTC), (), None if self.home.transport is not None else "home_service_unavailable"))

    async def _unavailable(self, owner_id: str, error: str) -> HomeContextSnapshot:
        snapshot = HomeContextSnapshot(owner_id, False, getattr(self.home.transport, "name", None), datetime.now(UTC), (), error)
        self._last[owner_id] = snapshot
        await self._emit("home.context_updated", owner_id, {"available": False, "error": error}, EventState.FAILED)
        return snapshot

    async def _emit(self, event_type: str, owner_id: str, payload: dict[str, object], state: EventState) -> None:
        event = Event.create(event_type, EventCategory.HOME, correlation_id=f"home-context-{owner_id}", actor_id=owner_id, payload={"owner_id": owner_id, **payload}, state=state)
        self.repository.append_event(event)
        await self.event_bus.publish(event)


class HomeRoutineService:
    """A small allowlisted template catalog; execution delegates to HomeActionService."""

    ROUTINES = (
        HomeRoutine("focus_lighting", "Focus lighting", "Apply configured focus lights", ({"domain": "light", "action": "turn_on"},)),
        HomeRoutine("study_lighting", "Study lighting", "Apply configured study lights", ({"domain": "light", "action": "turn_on"},)),
        HomeRoutine("work_start_scene", "Work start scene", "Turn on configured work lights", ({"domain": "light", "action": "turn_on"},)),
        HomeRoutine("sleep_scene", "Sleep scene", "Turn off configured lights", ({"domain": "light", "action": "turn_off"},)),
        HomeRoutine("leave_safe_scene", "Leave safe scene", "Turn off configured lights and switches", ({"domain": "light", "action": "turn_off"}, {"domain": "switch", "action": "turn_off"})),
        HomeRoutine("return_scene", "Return scene", "Turn on configured return lights", ({"domain": "light", "action": "turn_on"},)),
    )

    def __init__(self, context: HomeContextService, home: HomeActionService, repository: RuntimeRepository, event_bus: InMemoryEventBus) -> None:
        self.context = context
        self.home = home
        self.repository = repository
        self.event_bus = event_bus

    def list(self) -> tuple[HomeRoutine, ...]:
        return self.ROUTINES

    async def run(self, routine_id: str, identity: Identity, device: DeviceIdentity, *, dry_run: bool = True) -> RoutineRun:
        routine = next((item for item in self.ROUTINES if item.routine_id == routine_id), None)
        if routine is None:
            raise KeyError(routine_id)
        started = datetime.now(UTC)
        await self._emit("home.routine_started", identity.owner_id, routine_id, EventState.ACCEPTED)
        snapshot = await self.context.refresh(identity, device)
        results: list[dict[str, object]] = []
        entities = [item for item in snapshot.entities if isinstance(item, dict)]
        for template in routine.actions:
            for entity in entities:
                if entity.get("domain") != template["domain"]:
                    continue
                result = await self.home.execute(HomeAction(str(entity["entity_id"]), str(template["action"]), {}, dry_run), identity, device, correlation_id=f"routine-{routine_id}")
                results.append({"entity_id": entity["entity_id"], "action": template["action"], "status": result.status, "error_code": result.error_code})
        if not entities or not results:
            status = "partial" if snapshot.available else "unavailable"
        else:
            status = "completed" if all(item["status"] == "succeeded" for item in results) else "partial"
        run = RoutineRun(f"routine-run-{uuid4()}", identity.owner_id, routine_id, status, {"results": results, "home_available": snapshot.available}, started, datetime.now(UTC))
        self.repository.insert_routine_run(run)
        await self._emit("home.routine_partial" if status != "completed" else "home.routine_completed", identity.owner_id, routine_id, EventState.COMPLETED if status == "completed" else EventState.FAILED)
        return run

    async def _emit(self, event_type: str, owner_id: str, routine_id: str, state: EventState) -> None:
        event = Event.create(event_type, EventCategory.HOME, correlation_id=f"routine-{routine_id}", actor_id=owner_id, payload={"owner_id": owner_id, "routine_id": routine_id}, state=state)
        self.repository.append_event(event)
        await self.event_bus.publish(event)
