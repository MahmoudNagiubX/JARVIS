"""Presentation coordination over the existing notification authority."""

from __future__ import annotations

import hashlib
import inspect
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any, Awaitable, Callable
from uuid import uuid4

from ..attention.policy import AttentionContext, AttentionDecision, AttentionPolicy
from ..bus import InMemoryEventBus
from ..contracts import Notification
from ..events import Event, EventCategory, EventState
from ..persistence.repositories import RuntimeRepository
from ..presence.service import PresenceSnapshot
from ..voice.routing.service import VoiceRoutingService
from .service import NotificationService


Presentation = Callable[[Notification, str | None], bool | Awaitable[bool]]


@dataclass(frozen=True, slots=True)
class DeliveryAttempt:
    attempt_id: str
    owner_id: str
    notification_id: str
    channel: str
    target: str | None
    status: str
    reason: str | None
    fingerprint: str | None
    attempted_at: datetime
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    notification_id: str
    status: str
    channels: tuple[str, ...] = ()
    target_device: str | None = None
    target_voice_endpoint: str | None = None
    reason: str | None = None
    attempts: tuple[DeliveryAttempt, ...] = ()


class NotificationDeliveryCoordinator:
    """Selects real presentation adapters and records honest outcomes."""

    def __init__(
        self,
        notifications: NotificationService,
        attention: AttentionPolicy,
        presence: Any,
        voice_routing: VoiceRoutingService,
        repository: RuntimeRepository,
        event_bus: InMemoryEventBus,
        *,
        desktop: Presentation | None = None,
        voice: Presentation | None = None,
        personalization: Any | None = None,
        operations: Any | None = None,
        voice_core: Any | None = None,
    ) -> None:
        self.notifications = notifications
        self.attention = attention
        self.presence = presence
        self.voice_routing = voice_routing
        self.repository = repository
        self.event_bus = event_bus
        self.desktop = desktop
        self.voice = voice
        self.personalization = personalization
        self.operations = operations
        self.voice_core = voice_core
        self._queued: dict[str, set[str]] = {}

    async def deliver(
        self,
        owner_id: str,
        notification: Notification | str,
        *,
        mode: str = "normal",
        quiet_hours: tuple[str, str] | None = None,
        active_voice: bool = False,
        now: datetime | None = None,
    ) -> DeliveryResult:
        item = notification if isinstance(notification, Notification) else await self._find(owner_id, notification)
        if item is None or item.owner_id != owner_id:
            raise KeyError(notification if isinstance(notification, str) else notification.notification_id)
        current = now or datetime.now(UTC)
        presence = await self.presence.refresh(owner_id) if hasattr(self.presence, "refresh") else await self.presence.snapshot(owner_id, now=current)
        fingerprint = self._fingerprint(item)
        cooldown = 300.0
        if self.personalization is not None:
            profile = await self.personalization.get(owner_id)
            configured_quiet = profile.values.get("quiet_hours")
            if quiet_hours is None and isinstance(configured_quiet, (list, tuple)) and len(configured_quiet) == 2:
                quiet_hours = (str(configured_quiet[0]), str(configured_quiet[1]))
            announcement = str(profile.values.get("voice_announcement_level", "important"))
            cooldown = float(profile.values.get("voice_dedup_seconds", cooldown))
            timezone_name = profile.values.get("timezone") if isinstance(profile.values.get("timezone"), str) else None
        else:
            announcement = "important"
            timezone_name = None
        duplicate = any(
            row.get("fingerprint") == fingerprint and row.get("channel") == "voice" and row.get("status") == "delivered"
            and datetime.fromisoformat(str(row["attempted_at"])) >= current - timedelta(seconds=max(0.0, cooldown))
            for row in self.repository.delivery_attempts(owner_id, limit=100)
        )
        if self.operations is not None:
            mode = (await self.operations.mode(owner_id)).mode
        if self.voice_core is not None:
            active_voice = getattr(getattr(self.voice_core, "state", None), "value", None) in {"listening", "thinking", "speaking", "follow_up"}
        decision = self.attention.decide(item, presence, AttentionContext(mode, active_voice, duplicate, quiet_hours, announcement, timezone_name), now=current)
        await self._emit("notification.delivery_started", owner_id, item.notification_id, {"reason": decision.reason})
        if decision.suppress_duplicate:
            attempt = await self._attempt(owner_id, item, "voice", decision.target_voice_endpoint, "suppressed", decision.reason, fingerprint)
            await self._emit("notification.delivery_suppressed", owner_id, item.notification_id, {"reason": decision.reason})
            return DeliveryResult(item.notification_id, "suppressed_duplicate", (), decision.target_device, decision.target_voice_endpoint, decision.reason, (attempt,))
        attempts: list[DeliveryAttempt] = []
        channels: list[str] = []
        if (decision.visual_only or decision.voice_and_visual) and not decision.queue:
            # The HUD is the always-local presentation surface: the existing
            # notification-created event makes the record visible to the
            # projection, so this is an honest delivery rather than a fake OS
            # notification.
            attempts.append(await self._attempt(owner_id, item, "hud", None, "delivered", None, fingerprint))
            channels.append("hud")
            if self.desktop is None:
                attempts.append(await self._attempt(owner_id, item, "desktop", decision.target_device, "unavailable", "desktop_adapter_unavailable", fingerprint))
            else:
                attempts.append(await self._present(owner_id, item, "desktop", decision.target_device, self.desktop, fingerprint))
                if attempts[-1].status == "delivered":
                    channels.append("desktop")
        if decision.voice_and_visual or decision.voice_only:
            endpoint = await self.voice_routing.get(owner_id, decision.target_voice_endpoint) if decision.target_voice_endpoint else None
            if endpoint is None or not endpoint.online or not endpoint.output_enabled:
                attempts.append(await self._attempt(owner_id, item, "voice", decision.target_voice_endpoint, "unavailable", "voice_endpoint_unavailable", fingerprint))
            elif self.voice is None:
                attempts.append(await self._attempt(owner_id, item, "voice", endpoint.endpoint_id, "unavailable", "voice_adapter_unavailable", fingerprint))
            else:
                attempts.append(await self._present(owner_id, replace(item, message=item.message[:240]), "voice", endpoint.endpoint_id, self.voice, fingerprint))
                if attempts[-1].status == "delivered":
                    channels.append("voice")
        if decision.queue:
            status, reason = "queued", decision.reason
            queued = self._queued.setdefault(owner_id, set())
            if item.notification_id not in queued:
                queued.add(item.notification_id)
                attempts.append(await self._attempt(owner_id, item, "queue", None, "queued", reason, fingerprint))
                await self._emit("notification.delivery_queued", owner_id, item.notification_id, {"reason": reason})
        elif any(item.status == "delivered" for item in attempts):
            status, reason = "delivered", None
        elif attempts:
            status, reason = "unavailable", ";".join(dict.fromkeys(str(item.reason) for item in attempts if item.reason))
        else:
            status, reason = "suppressed", decision.reason
        if status == "delivered":
            try:
                await self.notifications.mark_delivered(owner_id, item.notification_id)
            except KeyError:
                # Direct adapter callers may supply an already-owned record;
                # the coordinator still records the presentation attempt.
                pass
            await self._emit("notification.delivered", owner_id, item.notification_id, {"channels": channels})
        elif status == "unavailable":
            await self._emit("notification.delivery_failed", owner_id, item.notification_id, {"reason": reason}, EventState.FAILED)
        return DeliveryResult(item.notification_id, status, tuple(channels), decision.target_device, decision.target_voice_endpoint, reason, tuple(attempts))

    async def reevaluate_queued(self, owner_id: str, *, now: datetime | None = None) -> tuple[DeliveryResult, ...]:
        results: list[DeliveryResult] = []
        queued = self._queued.get(owner_id, set())
        for notification_id in tuple(queued):
            item = await self._find(owner_id, notification_id)
            current = now or datetime.now(UTC)
            if item is None or item.dismissed_at is not None or item.expires_at is not None and item.expires_at <= current or item.delivered_at is not None:
                queued.discard(notification_id)
                continue
            result = await self.deliver(owner_id, item, now=current)
            results.append(result)
            if result.status != "queued":
                queued.discard(notification_id)
        return tuple(results)

    async def _find(self, owner_id: str, notification_id: str) -> Notification | None:
        for item in await self.notifications.list(owner_id):
            if item.notification_id == notification_id:
                return item
        return None

    async def deliver_notification(self, owner_id: str, notification_id: str, **kwargs: Any) -> DeliveryResult:
        return await self.deliver(owner_id, notification_id, **kwargs)

    async def _present(self, owner_id: str, item: Notification, channel: str, target: str | None, adapter: Presentation, fingerprint: str) -> DeliveryAttempt:
        try:
            result = adapter(item, target)
            delivered = bool(await result if inspect.isawaitable(result) else result)
            status, reason = ("delivered", None) if delivered else ("failed", "presentation_rejected")
        except Exception as exc:
            status, reason = "failed", f"presentation_error:{exc.__class__.__name__}"
        return await self._attempt(owner_id, item, channel, target, status, reason, fingerprint)

    async def _attempt(self, owner_id: str, item: Notification, channel: str, target: str | None, status: str, reason: str | None, fingerprint: str | None) -> DeliveryAttempt:
        attempt = DeliveryAttempt(f"delivery-{uuid4()}", owner_id, item.notification_id, channel, target, status, reason, fingerprint, datetime.now(UTC))
        self.repository.insert_delivery_attempt(attempt)
        return attempt

    async def _emit(self, event_type: str, owner_id: str, notification_id: str, payload: dict[str, object], state: EventState = EventState.EMITTED) -> None:
        event = Event.create(event_type, EventCategory.UI, correlation_id=f"notification-delivery-{notification_id}", actor_id=owner_id, payload={"owner_id": owner_id, "notification_id": notification_id, **payload}, state=state)
        self.repository.append_event(event)
        await self.event_bus.publish(event)

    @staticmethod
    def _fingerprint(item: Notification) -> str:
        return hashlib.sha256(f"{item.owner_id}|{item.title}|{item.message}".encode("utf-8")).hexdigest()
