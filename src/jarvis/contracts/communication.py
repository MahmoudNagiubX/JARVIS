"""Channel-neutral communication contracts."""

from __future__ import annotations

from collections.abc import Awaitable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol


@dataclass(frozen=True, slots=True)
class CommunicationMessage:
    message_id: str
    channel: str
    sender_id: str
    recipient: str
    content: str
    sent_at: datetime
    metadata: Mapping[str, object] = field(default_factory=dict)
    owner_id: str | None = None


class CommunicationAction(StrEnum):
    LIST = "list"
    READ = "read"
    SEARCH = "search"
    SUMMARIZE = "summarize"
    DRAFT = "draft"
    REPLY_DRAFT = "reply_draft"
    SEND = "send"
    MARK_READ = "mark_read"
    ARCHIVE = "archive"


@dataclass(frozen=True, slots=True)
class CommunicationThread:
    thread_id: str
    channel: str
    subject: str | None = None
    participants: tuple[str, ...] = ()
    message_ids: tuple[str, ...] = ()
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class CommunicationDraft:
    draft_id: str
    channel: str
    recipient: str
    content: str
    created_at: datetime
    reply_to: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CommunicationSendResult:
    status: str
    message_id: str | None = None
    approval_id: str | None = None
    error_code: str | None = None


class CommunicationProvider(Protocol):
    name: str

    def list_messages(self) -> Awaitable[tuple[CommunicationMessage, ...]]: ...

    def send(self, message: CommunicationMessage) -> Awaitable[bool]: ...


class CommunicationChannel(Protocol):
    name: str

    def send(self, message: CommunicationMessage) -> Awaitable[bool]: ...
