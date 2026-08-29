"""Storage records returned by the runtime repository."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class SessionRecord:
    id: str
    owner_id: str
    device_id: str
    status: str
    created_at: datetime
    last_seen_at: datetime
    closed_at: datetime | None


@dataclass(frozen=True, slots=True)
class ConversationRecord:
    id: str
    owner_id: str
    created_by_device_id: str
    title: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime | None


@dataclass(frozen=True, slots=True)
class MessageRecord:
    id: str
    conversation_id: str
    session_id: str | None
    run_id: str | None
    author_device_id: str | None
    role: str
    content: str
    ordinal: int
    client_message_id: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class RunRecord:
    id: str
    conversation_id: str
    session_id: str
    request_device_id: str
    trigger_message_id: str
    status: str
    created_at: datetime
    started_at: datetime | None
    cancel_requested_at: datetime | None
    completed_at: datetime | None
    model_request_id: str | None
    model_id: str | None
    model_digest: str | None
    finish_reason: str | None
    prompt_usage: int | None
    output_usage: int | None
    latency_ms: float | None
    failure_category: str | None
    failure_code: str | None
    correlation_id: str
    context: dict[str, Any]
    context_truncated: bool
    pending_approval_id: str | None
