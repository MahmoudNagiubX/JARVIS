"""Deterministic proactive finding contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class ProactiveFindingType(StrEnum):
    BUILD_FAILED = "build_failed"
    TESTS_REPEATEDLY_FAILING = "tests_repeatedly_failing"
    DEADLINE_APPROACHING = "deadline_approaching"
    GOAL_BLOCKED = "goal_blocked"
    DEV_SERVER_STOPPED = "dev_server_stopped"
    DEVICE_DISCONNECTED = "device_disconnected"
    TASK_STALLED = "task_stalled"
    OPERATION_COMPLETED = "operation_completed"
    APPROVAL_WAITING = "approval_waiting"
    DISK_SPACE_CRITICAL = "disk_space_critical"


class FindingStatus(StrEnum):
    DETECTED = "detected"
    ACKNOWLEDGED = "acknowledged"
    SUPPRESSED = "suppressed"
    ACTIONED = "actioned"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class ProactiveFinding:
    finding_id: str
    owner_id: str
    finding_type: str
    severity: str
    evidence: Mapping[str, object]
    source_events: tuple[str, ...]
    detected_at: datetime
    recommended_action: str | None = None
    auto_action_allowed: bool = False
    cooldown_seconds: int = 3600
    status: str = FindingStatus.DETECTED.value
    acknowledged_at: datetime | None = None
    last_notified_at: datetime | None = None
