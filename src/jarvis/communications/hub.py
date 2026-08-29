"""Read, draft, and policy-controlled send operations for communications."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from ..authority.approvals.service import DurableApprovalEngine
from ..authority.audit.service import DurableAuditService
from ..authority.permissions.engine import PolicyPermissionEngine
from ..autonomy.policy import AutonomyPolicy
from ..bus import InMemoryEventBus
from ..contracts import ApprovalRequest, AuditRecord, CommunicationDraft, CommunicationMessage, CommunicationProvider, CommunicationSendResult, CommunicationThread, DeviceIdentity, Identity
from ..events import Event, EventCategory, EventState
from ..persistence.repositories import RuntimeRepository


class LocalCommunicationChannel:
    """A deterministic local channel useful for offline operation and tests."""

    def __init__(self, name: str = "local") -> None:
        self.name = name
        self.messages: list[CommunicationMessage] = []

    async def list_messages(self) -> tuple[CommunicationMessage, ...]:
        return tuple(self.messages)

    async def send(self, message: CommunicationMessage) -> bool:
        self.messages.append(message)
        return True


class CommunicationsHub:
    """Normalize channel messages and make every send auditable/policy-bound."""

    def __init__(self, repository: RuntimeRepository, event_bus: InMemoryEventBus, approvals: DurableApprovalEngine, permission: PolicyPermissionEngine, audit: DurableAuditService, autonomy: AutonomyPolicy | None = None) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.approvals = approvals
        self.permission = permission
        self.audit = audit
        self.autonomy = autonomy or AutonomyPolicy()
        self.channels: dict[str, CommunicationProvider] = {}
        self._messages: dict[str, list[CommunicationMessage]] = {}
        self._drafts: dict[str, CommunicationDraft] = {}
        self._pending: dict[str, tuple[str, CommunicationMessage, Identity, DeviceIdentity]] = {}

    def register_channel(self, channel: CommunicationProvider) -> None:
        if not channel.name.strip():
            raise ValueError("communication channel name is required")
        self.channels[channel.name] = channel

    def list_channels(self) -> tuple[str, ...]:
        return tuple(sorted(self.channels))

    async def sync(self, owner_id: str, channel_name: str) -> tuple[CommunicationMessage, ...]:
        channel = self.channels.get(channel_name)
        if channel is None:
            raise KeyError(channel_name)
        messages = await channel.list_messages()
        normalized = []
        for message in messages:
            item = message if message.owner_id == owner_id else CommunicationMessage(message.message_id, message.channel, message.sender_id, message.recipient, message.content, message.sent_at, message.metadata, owner_id)
            normalized.append(item)
        self._messages.setdefault(owner_id, [])
        self._messages[owner_id] = [item for item in self._messages[owner_id] if item.channel != channel_name] + normalized
        for message in normalized:
            await self._emit("communication.received", owner_id, {"message_id": message.message_id, "channel": channel_name})
        return tuple(normalized)

    async def list_messages(self, owner_id: str, channel: str | None = None, query: str | None = None) -> tuple[CommunicationMessage, ...]:
        values = self._messages.get(owner_id, [])
        if channel:
            values = [item for item in values if item.channel == channel]
        if query:
            needle = query.casefold()
            values = [item for item in values if needle in item.content.casefold() or needle in item.sender_id.casefold() or needle in item.recipient.casefold()]
        return tuple(sorted(values, key=lambda item: item.sent_at, reverse=True))

    async def read(self, owner_id: str, message_id: str) -> CommunicationMessage | None:
        return next((item for item in self._messages.get(owner_id, []) if item.message_id == message_id), None)

    async def search(self, owner_id: str, query: str, channel: str | None = None) -> tuple[CommunicationMessage, ...]:
        return await self.list_messages(owner_id, channel, query)

    async def summarize(self, owner_id: str, message_id: str, max_words: int = 80) -> str:
        message = await self.read(owner_id, message_id)
        if message is None:
            raise KeyError(message_id)
        words = message.content.split()
        summary = " ".join(words[:max(1, max_words)])
        return summary + (" ..." if len(words) > max_words else "")

    async def reply_draft(self, owner_id: str, message_id: str, content: str) -> CommunicationDraft:
        message = await self.read(owner_id, message_id)
        if message is None:
            raise KeyError(message_id)
        return await self.draft(owner_id, message.channel, message.sender_id, content, message_id)

    async def mark_read(self, owner_id: str, message_id: str) -> CommunicationMessage:
        return await self._update_message(owner_id, message_id, {"read": True})

    async def archive(self, owner_id: str, message_id: str) -> CommunicationMessage:
        return await self._update_message(owner_id, message_id, {"archived": True})

    async def _update_message(self, owner_id: str, message_id: str, metadata: Mapping[str, object]) -> CommunicationMessage:
        message = await self.read(owner_id, message_id)
        if message is None:
            raise KeyError(message_id)
        updated = replace(message, metadata=dict(message.metadata) | dict(metadata))
        values = self._messages[owner_id]
        self._messages[owner_id] = [updated if item.message_id == message_id else item for item in values]
        return updated

    async def draft(self, owner_id: str, channel: str, recipient: str, content: str, reply_to: str | None = None, metadata: Mapping[str, object] | None = None) -> CommunicationDraft:
        if channel not in self.channels:
            raise KeyError(channel)
        if not recipient.strip() or not content.strip():
            raise ValueError("draft recipient and content are required")
        draft = CommunicationDraft(f"draft-{uuid4()}", channel, recipient.strip(), content.strip(), datetime.now(UTC), reply_to, dict(metadata or {}))
        self._drafts[draft.draft_id] = draft
        await self._emit("communication.draft_created", owner_id, {"draft_id": draft.draft_id, "channel": channel})
        return draft

    async def send(self, owner_id: str, channel: str, recipient: str, content: str, identity: Identity, device: DeviceIdentity, *, important: bool = False, session_id: str = "communication") -> CommunicationSendResult:
        provider = self.channels.get(channel)
        if provider is None:
            return CommunicationSendResult("failed", error_code="communication_channel_unavailable")
        if not recipient.strip() or not content.strip():
            return CommunicationSendResult("failed", error_code="message_required")
        permission = await self.permission.evaluate(identity, device, "communication.send", {"required_scope": "tool.request", "required_capabilities": frozenset({"communication.send"}), "risk_level": "consequential" if important else "read"})
        autonomy = self.autonomy.decide("message.send.important" if important else "message.send")
        message = CommunicationMessage(f"message-{uuid4()}", channel, identity.identity_id, recipient.strip(), content.strip(), datetime.now(UTC), {"important": important}, owner_id)
        if permission.effect.value == "deny":
            await self.audit.record(AuditRecord(f"audit-{uuid4()}", "communication.send_denied", datetime.now(UTC), identity.identity_id, device.device_id, f"communication-{owner_id}", "denied", permission.reason_code, {"channel": channel, "recipient": recipient}))
            return CommunicationSendResult("denied", error_code=permission.reason_code)
        if permission.effect.value == "require_approval" or autonomy.requires_approval or not autonomy.allowed:
            approval_id = f"approval-{uuid4()}"
            await self.approvals.request(ApprovalRequest(approval_id, "communication.send", owner_id, device.device_id, "communication send requires approval", datetime.now(UTC), datetime.now(UTC) + timedelta(minutes=10), {"channel": channel, "recipient": recipient, "content": content, "important": important, "message_id": message.message_id}))
            self._pending[approval_id] = (owner_id, message, identity, device)
            await self._emit("communication.send_requested", owner_id, {"approval_id": approval_id, "message_id": message.message_id}, EventState.ACCEPTED)
            return CommunicationSendResult("approval_required", message.message_id, approval_id)
        return await self._deliver(owner_id, provider, message, session_id)

    async def _send_scoped_auto_verified(self, owner_id: str, channel: str, recipient: str, content: str, identity: Identity, device: DeviceIdentity, *, rule_id: str, session_id: str = "communication-auto") -> CommunicationSendResult:
        """Internal-only delivery reached after persisted-rule validation."""
        provider = self.channels.get(channel)
        if provider is None:
            return CommunicationSendResult("failed", error_code="communication_channel_unavailable")
        permission = await self.permission.evaluate(identity, device, "communication.send", {"required_scope": "tool.request", "required_capabilities": frozenset({"communication.send"}), "risk_level": "consequential"})
        autonomy = self.autonomy.decide("message.send.scoped_auto")
        if permission.effect.value == "deny" or not autonomy.allowed or autonomy.requires_approval:
            return CommunicationSendResult("denied", error_code=permission.reason_code if permission.effect.value == "deny" else "scoped_auto_denied")
        message = CommunicationMessage(f"message-{uuid4()}", channel, identity.identity_id, recipient.strip(), content.strip(), datetime.now(UTC), {"scoped_auto_rule_id": rule_id}, owner_id)
        return await self._deliver(owner_id, provider, message, session_id)

    async def decide_send(self, owner_id: str, approval_id: str, approved: bool, decided_by: str) -> CommunicationSendResult:
        pending = self._pending.get(approval_id)
        if pending is None or pending[0] != owner_id:
            raise KeyError(approval_id)
        decision = await self.approvals.decide(approval_id, approved, decided_by)
        self._pending.pop(approval_id, None)
        if decision.status.value != "approved":
            await self._emit("communication.failed", owner_id, {"approval_id": approval_id, "reason": decision.status.value}, EventState.FAILED)
            return CommunicationSendResult("denied", pending[1].message_id, approval_id, decision.status.value)
        return await self._deliver(owner_id, self.channels[pending[1].channel], pending[1], "communication")

    async def _deliver(self, owner_id: str, provider: CommunicationProvider, message: CommunicationMessage, session_id: str) -> CommunicationSendResult:
        await self._emit("communication.send_requested", owner_id, {"message_id": message.message_id}, EventState.ACCEPTED)
        try:
            sent = provider.send(message)
            sent = await sent if inspect.isawaitable(sent) else sent
        except Exception as exc:
            sent = False
            error = exc.__class__.__name__
        else:
            error = None
        if not sent:
            await self._emit("communication.failed", owner_id, {"message_id": message.message_id, "error_code": error or "channel_send_failed"}, EventState.FAILED)
            await self.audit.record(AuditRecord(f"audit-{uuid4()}", "communication.failed", datetime.now(UTC), message.sender_id, None, f"communication-{owner_id}", "failed", error, {"channel": message.channel}))
            return CommunicationSendResult("failed", message.message_id, error_code=error or "channel_send_failed")
        self._messages.setdefault(owner_id, []).append(message)
        await self._emit("communication.sent", owner_id, {"message_id": message.message_id, "channel": message.channel}, EventState.COMPLETED)
        await self.audit.record(AuditRecord(f"audit-{uuid4()}", "communication.sent", datetime.now(UTC), message.sender_id, None, f"communication-{owner_id}", "sent", None, {"channel": message.channel, "session_id": session_id}))
        return CommunicationSendResult("sent", message.message_id)

    async def _emit(self, event_type: str, owner_id: str, payload: dict[str, object], state: EventState = EventState.EMITTED) -> None:
        event = Event.create(event_type, EventCategory.COMMUNICATION, correlation_id=f"communication-{owner_id}", actor_id=owner_id, payload=payload, state=state)
        self.repository.append_event(event)
        await self.event_bus.publish(event)
