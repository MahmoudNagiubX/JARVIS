"""Normalized product event model used across all JARVIS boundaries."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Mapping
from uuid import uuid4


class EventCategory(StrEnum):
    SYSTEM = "system"
    CONVERSATION = "conversation"
    AGENT = "agent"
    WORKER = "worker"
    TOOL = "tool"
    APPROVAL = "approval"
    MODEL = "model"
    VOICE = "voice"
    DEVICE = "device"
    COMPUTER = "computer"
    HOME = "home"
    BROWSER = "browser"
    MEMORY = "memory"
    WORLD_STATE = "world_state"
    GOAL = "goal"
    COMMUNICATION = "communication"
    ENGINEERING = "engineering"
    UI = "ui"
    PERSONALIZATION = "personalization"
    PROACTIVE = "proactive"
    NODE = "node"
    EXPERIENCE = "experience"
    RESEARCH = "research"
    PERCEPTION = "perception"
    DEVELOPER_WORKER = "developer_worker"
    MISSION = "mission"
    SKILL = "skill"
    AUTOMATION = "automation"
    BRIEFING = "briefing"
    INTELLIGENCE = "intelligence"
    EVALUATION = "evaluation"
    WORKSPACE = "workspace"


class EventSeverity(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class EventState(StrEnum):
    EMITTED = "emitted"
    ACCEPTED = "accepted"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Event:
    """Immutable envelope with correlation and causation metadata."""

    event_id: str
    event_type: str
    category: EventCategory
    timestamp: datetime
    correlation_id: str
    causation_id: str | None
    session_id: str | None
    actor_id: str | None
    payload: Mapping[str, Any] = field(default_factory=dict)
    severity: EventSeverity = EventSeverity.INFO
    state: EventState = EventState.EMITTED

    def __post_init__(self) -> None:
        if not self.event_id.strip():
            raise ValueError("event_id cannot be empty")
        if not self.event_type.strip():
            raise ValueError("event_type cannot be empty")
        if not self.correlation_id.strip():
            raise ValueError("correlation_id cannot be empty")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")

    @classmethod
    def create(
        cls,
        event_type: str,
        category: EventCategory,
        *,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        session_id: str | None = None,
        actor_id: str | None = None,
        payload: Mapping[str, Any] | None = None,
        severity: EventSeverity = EventSeverity.INFO,
        state: EventState = EventState.EMITTED,
    ) -> "Event":
        return cls(
            event_id=str(uuid4()),
            event_type=event_type,
            category=category,
            timestamp=datetime.now(UTC),
            correlation_id=correlation_id or str(uuid4()),
            causation_id=causation_id,
            session_id=session_id,
            actor_id=actor_id,
            payload=dict(payload or {}),
            severity=severity,
            state=state,
        )
