"""Concise briefings assembled only from durable structured facts."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from ..bus import InMemoryEventBus
from ..events import Event, EventCategory, EventState
from ..persistence.repositories import RuntimeRepository


@dataclass(frozen=True, slots=True)
class Briefing:
    briefing_id: str
    owner_id: str
    briefing_type: str
    title: str
    summary: str
    items: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    created_at: datetime
    delivered_at: datetime | None = None
    dismissed_at: datetime | None = None
    dedup_key: str = ""


class BriefingService:
    TYPES = frozenset({"morning", "work_start", "project", "system", "deadline", "end_of_day", "weekly"})

    def __init__(self, repository: RuntimeRepository, event_bus: InMemoryEventBus, *, dedup_seconds: float = 900.0) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.dedup_seconds = max(60.0, dedup_seconds)
        self._items: dict[str, Briefing] = {}

    async def generate(self, owner_id: str, briefing_type: str = "morning", *, project_id: str | None = None) -> Briefing | None:
        if briefing_type not in self.TYPES:
            raise ValueError("unsupported briefing type")
        lines: list[str] = []
        evidence: list[str] = []
        goals = [row for row in self.repository.goals(owner_id) if str(row.get("status")) not in {"completed", "cancelled"}]
        for goal in goals[:5]:
            lines.append(f"Goal: {str(goal.get('title') or goal.get('description') or goal.get('id'))[:160]}")
            evidence.append(f"goal:{goal['id']}")
        missions = [row for row in self.repository.missions(owner_id) if str(row.get("status")) not in {"completed", "cancelled"}]
        for mission in missions[:5]:
            lines.append(f"Mission {mission['status']}: {str(mission['title'])[:140]}")
            evidence.append(f"mission:{mission['id']}")
        projects = self.repository.workspace_projects(owner_id)
        if project_id:
            projects = [item for item in projects if str(item.get("id")) == project_id]
        for project in projects[:3]:
            metadata = self._json(project.get("metadata_json"))
            status = str(metadata.get("git_status", project.get("project_type", "unknown")))
            changed = len(metadata.get("recent_files", ())) if isinstance(metadata.get("recent_files"), list) else 0
            lines.append(f"Project {project['id']}: {status}; {changed} recent changed file(s)")
            evidence.append(f"project:{project['id']}")
        findings = self.repository.intelligence_findings(owner_id, True)
        for finding in findings[:5]:
            lines.append(f"Finding ({finding['severity']}): {str(finding['recommended_action'])[:160]}")
            evidence.append(f"finding:{finding['id']}")
        approvals = self.repository.pending_approvals(owner_id)
        if approvals:
            lines.append(f"Pending approvals: {len(approvals)}")
            evidence.extend(f"approval:{item['id']}" for item in approvals[:5])
        if not lines:
            return None
        dedup_key = f"{owner_id}:{briefing_type}:{project_id or 'all'}:" + "|".join(evidence)
        for item in self._items.values():
            if item.owner_id == owner_id and item.dedup_key == dedup_key and datetime.now(UTC) - item.created_at < timedelta(seconds=self.dedup_seconds):
                return item
        for row in self.repository.briefings(owner_id, briefing_type):
            if row.get("dedup_key") == dedup_key:
                created = self._time(row.get("created_at"))
                if created and datetime.now(UTC) - created < timedelta(seconds=self.dedup_seconds):
                    return self._from_row(row)
        briefing = Briefing(f"briefing-{uuid4()}", owner_id, briefing_type, f"JARVIS {briefing_type.replace('_', ' ').title()} Brief", " ".join(lines), tuple(lines), tuple(dict.fromkeys(evidence)), datetime.now(UTC), dedup_key=dedup_key)
        self._items[briefing.briefing_id] = briefing
        self.repository.insert_briefing(briefing)
        await self._emit("briefing.created", briefing, EventState.COMPLETED)
        return briefing

    async def deliver(self, owner_id: str, briefing_id: str) -> Briefing:
        item = self._required(owner_id, briefing_id)
        updated = replace(item, delivered_at=datetime.now(UTC))
        self._items[briefing_id] = updated
        self.repository.insert_briefing(updated)
        await self._emit("briefing.delivered", updated, EventState.COMPLETED)
        return updated

    async def dismiss(self, owner_id: str, briefing_id: str) -> Briefing:
        item = self._required(owner_id, briefing_id)
        updated = replace(item, dismissed_at=datetime.now(UTC))
        self._items[briefing_id] = updated
        self.repository.insert_briefing(updated)
        await self._emit("briefing.dismissed", updated, EventState.COMPLETED)
        return updated

    async def list(self, owner_id: str, briefing_type: str | None = None) -> tuple[Briefing, ...]:
        values = list(self._items.values())
        known = {item.briefing_id for item in values}
        values.extend(self._from_row(row) for row in self.repository.briefings(owner_id, briefing_type) if str(row["id"]) not in known)
        return tuple(item for item in sorted(values, key=lambda item: item.created_at, reverse=True) if item.owner_id == owner_id and (briefing_type is None or item.briefing_type == briefing_type))

    def _required(self, owner_id: str, briefing_id: str) -> Briefing:
        item = self._items.get(briefing_id)
        if item is None:
            row = next((row for row in self.repository.briefings(owner_id) if row["id"] == briefing_id), None)
            item = self._from_row(row) if row else None
        if item is None or item.owner_id != owner_id:
            raise KeyError(briefing_id)
        return item

    async def _emit(self, name: str, briefing: Briefing, state: EventState) -> None:
        event = Event.create(name, EventCategory.BRIEFING, correlation_id=briefing.briefing_id, actor_id=briefing.owner_id, payload={"owner_id": briefing.owner_id, "briefing_id": briefing.briefing_id, "briefing_type": briefing.briefing_type, "evidence_ids": list(briefing.evidence_ids)}, state=state)
        self.repository.append_event(event)
        await self.event_bus.publish(event)

    @staticmethod
    def _json(value: object) -> dict[str, Any]:
        if isinstance(value, str):
            try:
                loaded = json.loads(value)
                return loaded if isinstance(loaded, dict) else {}
            except json.JSONDecodeError:
                return {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _time(value: object) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
        except ValueError:
            return None

    @staticmethod
    def _from_row(row: Any) -> Briefing:
        def sequence(value: object) -> tuple[str, ...]:
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    return ()
            return tuple(str(item) for item in value) if isinstance(value, list) else ()
        return Briefing(str(row["id"]), str(row["owner_id"]), str(row["briefing_type"]), str(row["title"]), str(row["summary"]), sequence(row["items_json"]), sequence(row["evidence_ids_json"]), BriefingService._time(row["created_at"]) or datetime.now(UTC), BriefingService._time(row.get("delivered_at")), BriefingService._time(row.get("dismissed_at")), str(row["dedup_key"]))
