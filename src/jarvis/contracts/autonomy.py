"""Explicit autonomy levels for proactive and agent actions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class AutonomyLevel(IntEnum):
    OBSERVE = 0
    SAFE_AUTO = 1
    AUTO_NOTIFY = 2
    APPROVAL_REQUIRED = 3
    BLOCKED = 4


@dataclass(frozen=True, slots=True)
class AutonomyDecision:
    action: str
    level: AutonomyLevel
    allowed: bool
    requires_approval: bool
    reason: str


@dataclass(frozen=True, slots=True)
class AutonomyRule:
    action_prefix: str
    level: AutonomyLevel
    reason: str
