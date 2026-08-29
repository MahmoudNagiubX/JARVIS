"""Channel-neutral communication contracts."""

from __future__ import annotations

from collections.abc import Awaitable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
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


class CommunicationChannel(Protocol):
    name: str

    def send(self, message: CommunicationMessage) -> Awaitable[bool]: ...
