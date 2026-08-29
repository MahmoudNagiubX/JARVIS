"""Bounded local notification creation, deduplication, and delivery."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from uuid import uuid4

from ..authority.audit.service import DurableAuditService
from ..bus import InMemoryEventBus
from ..contracts import AuditRecord, Notification
from ..events import Event, EventCategory, EventState
from ..persistence.repositories import RuntimeRepository


Delivery = Callable[[Notification], bool | Awaitable[bool]]


class NotificationService:
    """Notification store with cooldown-style deduplication and local delivery."""

    def __init__(self, repository: RuntimeRepository, event_bus: InMemoryEventBus, audit: DurableAuditService | None = None, delivery: Delivery | None = None) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.audit = audit
        self.delivery = delivery
        self._items: dict[str, Notification] = {}

    async def create(self, owner_id: str, title: str, message: str, *, severity: str = "info", source: str = "runtime", action_options: tuple[str, ...] = (), target_device: str | None = None, expires_at: datetime | None = None, dedup_key: str | None = None, metadata: Mapping[str, object] | None = None) -> Notification:
        if not title.strip() or not message.strip():
            raise ValueError("notification title and message are required")
        if dedup_key:
            now = datetime.now(UTC)
            for item in self._items.values():
                if item.owner_id == owner_id and item.dedup_key == dedup_key and item.dismissed_at is None and (item.expires_at is None or item.expires_at > now):
                    return item
        notification = Notification(f"notification-{uuid4()}", title.strip(), message.strip(), severity, source, tuple(action_options), target_device, expires_at, dedup_key, datetime.now(UTC), owner_id=owner_id, metadata=dict(metadata or {}))
        self._items[notification.notification_id] = notification
        await self._emit("notification.created", owner_id, {"notification_id": notification.notification_id, "severity": severity, "source": source})
        return notification

    async def deliver(self, owner_id: str, notification_id: str) -> Notification:
        current = self._required(owner_id, notification_id)
        if self.delivery is None:
            raise RuntimeError("notification_delivery_not_configured")
        result = self.delivery(current)
        delivered = bool(await result if inspect.isawaitable(result) else result)
        if not delivered:
            raise RuntimeError("notification_delivery_failed")
        updated = Notification(current.notification_id, current.title, current.message, current.severity, current.source, current.action_options, current.target_device, current.expires_at, current.dedup_key, current.created_at, datetime.now(UTC), current.dismissed_at, current.metadata, current.owner_id)
        self._items[notification_id] = updated
        await self._emit("notification.delivered", owner_id, {"notification_id": notification_id}, EventState.COMPLETED)
        return updated

    async def dismiss(self, owner_id: str, notification_id: str) -> Notification:
        current = self._required(owner_id, notification_id)
        updated = Notification(current.notification_id, current.title, current.message, current.severity, current.source, current.action_options, current.target_device, current.expires_at, current.dedup_key, current.created_at, current.delivered_at, datetime.now(UTC), current.metadata, current.owner_id)
        self._items[notification_id] = updated
        await self._emit("notification.dismissed", owner_id, {"notification_id": notification_id}, EventState.COMPLETED)
        return updated

    async def list(self, owner_id: str, active_only: bool = False) -> tuple[Notification, ...]:
        now = datetime.now(UTC)
        values = [item for item in self._items.values() if item.owner_id == owner_id and (not active_only or item.dismissed_at is None) and (item.expires_at is None or item.expires_at > now)]
        return tuple(sorted(values, key=lambda item: item.created_at or datetime.min.replace(tzinfo=UTC), reverse=True))

    def _required(self, owner_id: str, notification_id: str) -> Notification:
        item = self._items.get(notification_id)
        if item is None or item.owner_id != owner_id:
            raise KeyError(notification_id)
        return item

    async def _emit(self, event_type: str, owner_id: str, payload: dict[str, object], state: EventState = EventState.EMITTED) -> None:
        event = Event.create(event_type, EventCategory.UI, correlation_id=f"notification-{owner_id}", actor_id=owner_id, payload=payload, state=state)
        self.repository.append_event(event)
        await self.event_bus.publish(event)
        if self.audit:
            await self.audit.record(AuditRecord(f"audit-{uuid4()}", event_type, datetime.now(UTC), owner_id, None, f"notification-{owner_id}", state.value, None, payload))
