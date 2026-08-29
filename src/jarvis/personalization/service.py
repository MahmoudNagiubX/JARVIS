"""Inspectible style preferences and bounded preference learning."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from uuid import uuid4

from ..authority.audit.service import DurableAuditService
from ..bus import InMemoryEventBus
from ..contracts import AuditRecord, PersonalizationProfile, PersonalizationUpdate
from ..events import Event, EventCategory, EventState
from ..persistence.repositories import RuntimeRepository


class DurablePersonalizationService:
    DEFAULTS = {
        "preferred_name": "Mahmoud",
        "alternate_address": "Sir",
        "assistant_name": "JARVIS",
        "verbosity": "concise",
        "tone": "calm/formal/intelligent",
        "language_mode": "Egyptian Arabic + English technical terms",
        "notification_tolerance": "normal",
        "briefing_preference": "morning",
        "worker_preference": "local_first",
        "response_length": "concise",
    }
    ALLOWED_KEYS = set(DEFAULTS) | {"preferred_tools", "common_project_directories", "usual_work_periods", "common_workflows", "notification_dismissal_patterns", "briefing_preference", "worker_preference", "response_length"}

    def __init__(self, repository: RuntimeRepository, event_bus: InMemoryEventBus, audit: DurableAuditService | None = None) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.audit = audit

    async def get(self, owner_id: str) -> PersonalizationProfile:
        values = dict(self.DEFAULTS)
        for row in self.repository.personalization(owner_id):
            values[row["key"]] = json.loads(row["value_json"])
        rows = self.repository.personalization(owner_id)
        updated = max((datetime.fromisoformat(row["updated_at"]) for row in rows), default=None)
        return PersonalizationProfile(owner_id, values, updated)

    async def update(self, owner_id: str, update: PersonalizationUpdate) -> PersonalizationProfile:
        key = update.key.strip()
        if key not in self.ALLOWED_KEYS:
            raise ValueError("personalization key is not editable")
        if isinstance(update.value, str) and len(update.value) > 500:
            raise ValueError("personalization value is too long")
        if len(json.dumps(update.value, ensure_ascii=False, default=str)) > 2000 or any(token in key.casefold() for token in ("secret", "password", "credential", "token")):
            raise ValueError("personalization value is not allowed")
        self.repository.set_personalization(owner_id, key, update.value, update.source)
        await self._audit(owner_id, "personalization.updated", {"key": key, "source": update.source})
        await self._emit("personalization.updated", owner_id, {"key": key, "source": update.source}, EventState.COMPLETED)
        return await self.get(owner_id)

    async def patch(self, owner_id: str, values: dict[str, object], source: str = "user") -> PersonalizationProfile:
        profile = await self.get(owner_id)
        for key, value in values.items():
            profile = await self.update(owner_id, PersonalizationUpdate(key, value, source))
        return profile

    async def learn_from_text(self, owner_id: str, text: str) -> tuple[str, ...]:
        lowered = text.casefold()
        learned: list[str] = []
        if re.search(r"keep (your|the) answers? short|be concise|short answers", lowered):
            await self.update(owner_id, PersonalizationUpdate("verbosity", "concise", "conversation"))
            learned.append("verbosity")
        match = re.search(r"(?:call me|my name is) ([A-Za-z][\w -]{1,50})", text, re.I)
        if match:
            await self.update(owner_id, PersonalizationUpdate("preferred_name", match.group(1).strip(" .,!?") , "conversation"))
            learned.append("preferred_name")
        tool_match = re.search(r"(?:prefer|use|choose)\s+(?:the\s+)?([a-z][a-z0-9_.-]{2,40})\s+tool", lowered)
        if tool_match:
            profile = await self.get(owner_id)
            tools = list(profile.values.get("preferred_tools", [])) if isinstance(profile.values.get("preferred_tools"), list) else []
            if tool_match.group(1) not in tools:
                tools.append(tool_match.group(1))
            await self.update(owner_id, PersonalizationUpdate("preferred_tools", tools[-20:], "conversation"))
            learned.append("preferred_tools")
        period_match = re.search(r"(?:usually|normally)\s+work(?:s)?\s+([^.!?]{2,80})", lowered)
        if period_match:
            await self.update(owner_id, PersonalizationUpdate("usual_work_periods", [period_match.group(1).strip()], "conversation"))
            learned.append("usual_work_periods")
        workflow_match = re.search(r"(?:workflow|when i)\s*[: ]\s*([^.!?]{2,100})", text, re.I)
        if workflow_match:
            await self.update(owner_id, PersonalizationUpdate("common_workflows", [workflow_match.group(1).strip()[:100]], "conversation"))
            learned.append("common_workflows")
        if re.search(r"\b(morning|daily) brief", lowered):
            await self.update(owner_id, PersonalizationUpdate("briefing_preference", "morning", "conversation"))
            learned.append("briefing_preference")
        if re.search(r"\b(short|concise|brief) responses?\b", lowered):
            await self.update(owner_id, PersonalizationUpdate("response_length", "short", "conversation"))
            learned.append("response_length")
        return tuple(learned)

    async def delete(self, owner_id: str, key: str) -> PersonalizationProfile:
        if key not in self.ALLOWED_KEYS:
            raise ValueError("personalization key is not editable")
        self.repository.delete_personalization(owner_id, key)
        await self._audit(owner_id, "personalization.updated", {"key": key, "action": "reset"})
        await self._emit("personalization.updated", owner_id, {"key": key, "action": "reset"}, EventState.COMPLETED)
        return await self.get(owner_id)

    async def _audit(self, owner_id: str, event_type: str, metadata: dict[str, object]) -> None:
        if self.audit:
            await self.audit.record(AuditRecord(f"audit-{uuid4()}", event_type, datetime.now(UTC), owner_id, None, f"personalization-{owner_id}", "updated", None, metadata))

    async def _emit(self, event_type: str, owner_id: str, payload: dict[str, object], state: EventState = EventState.EMITTED) -> None:
        event = Event.create(event_type, EventCategory.PERSONALIZATION, correlation_id=f"personalization-{owner_id}", actor_id=owner_id, payload=payload, state=state)
        self.repository.append_event(event)
        await self.event_bus.publish(event)
