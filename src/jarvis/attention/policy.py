"""Small, inspectable delivery policy; it never creates or mutates notifications."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Mapping

from ..contracts import Notification
from ..presence.service import PresenceSnapshot
from ..time_windows import in_time_window


class AttentionLevel(StrEnum):
    INFO = "info"
    IMPORTANT = "important"
    URGENT = "urgent"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class AttentionContext:
    mode: str = "normal"
    active_voice: bool = False
    duplicate: bool = False
    quiet_hours: tuple[str, str] | None = None
    voice_announcement_level: str = "important"


@dataclass(frozen=True, slots=True)
class AttentionDecision:
    deliver_now: bool
    queue: bool
    visual_only: bool
    voice_and_visual: bool
    voice_only: bool
    suppress_duplicate: bool
    escalate: bool
    target_device: str | None
    target_voice_endpoint: str | None
    reason: str


class AttentionPolicy:
    """Delivery behavior only. Urgency cannot grant action authority."""

    def decide(
        self,
        notification: Notification,
        presence: PresenceSnapshot,
        context: AttentionContext | None = None,
        *,
        now: datetime | None = None,
    ) -> AttentionDecision:
        context = context or AttentionContext()
        level = notification.severity.casefold()
        if context.duplicate:
            return AttentionDecision(False, False, False, False, False, True, False, presence.active_device_id, presence.voice_endpoint_id, "duplicate_cooldown")
        if context.mode in {"sleep", "do_not_disturb", "away"} and level not in {AttentionLevel.URGENT, AttentionLevel.CRITICAL}:
            return AttentionDecision(False, True, True, False, False, False, False, presence.active_device_id, None, f"mode_{context.mode}")
        if context.quiet_hours and self._in_window(context.quiet_hours, now or datetime.now(UTC)) and level not in {AttentionLevel.URGENT, AttentionLevel.CRITICAL}:
            return AttentionDecision(False, True, True, False, False, False, False, presence.active_device_id, None, "quiet_hours")
        if context.mode in {"focus", "study", "meeting"} and level == AttentionLevel.INFO:
            return AttentionDecision(False, True, True, False, False, False, False, presence.active_device_id, None, f"mode_{context.mode}")
        if level == AttentionLevel.CRITICAL:
            return AttentionDecision(True, False, False, True, False, False, True, presence.active_device_id, presence.voice_endpoint_id, "critical")
        if level == AttentionLevel.URGENT:
            return AttentionDecision(True, False, False, True, False, False, True, presence.active_device_id, presence.voice_endpoint_id, "urgent")
        if context.voice_announcement_level in {"all", "important"} and level == AttentionLevel.IMPORTANT and not context.active_voice:
            return AttentionDecision(True, False, False, True, False, False, False, presence.active_device_id, presence.voice_endpoint_id, "important")
        return AttentionDecision(True, False, True, False, False, False, False, presence.active_device_id, None, "visual_default")

    @staticmethod
    def _in_window(window: tuple[str, str], current: datetime) -> bool:
        return in_time_window(window[0], window[1], now=current)
