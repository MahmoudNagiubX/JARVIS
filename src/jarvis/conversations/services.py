"""Thin domain services over the single runtime repository."""

from __future__ import annotations

from ..persistence.models import ConversationRecord, SessionRecord
from ..persistence.repositories import RuntimeRepository


class SessionService:
    def __init__(self, repository: RuntimeRepository) -> None:
        self.repository = repository

    async def create(self, owner_id: str, device_id: str) -> SessionRecord:
        return self.repository.create_session(owner_id, device_id)

    async def close(self, session_id: str) -> None:
        self.repository.close_session(session_id)


class ConversationService:
    def __init__(self, repository: RuntimeRepository) -> None:
        self.repository = repository

    async def create(self, owner_id: str, device_id: str, title: str | None = None) -> ConversationRecord:
        return self.repository.create_conversation(owner_id, device_id, title.strip() if title else None)

    async def get(self, conversation_id: str) -> ConversationRecord | None:
        return self.repository.conversation(conversation_id)

    async def messages(self, conversation_id: str):
        return tuple(self.repository.messages(conversation_id))


class RunService:
    def __init__(self, repository: RuntimeRepository) -> None:
        self.repository = repository

    async def get(self, run_id: str):
        return self.repository.run(run_id)
