"""Approval workflow contracts for consequential operations."""

from __future__ import annotations

from collections.abc import Awaitable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    approval_id: str
    action: str
    requester_id: str
    device_id: str | None
    reason: str
    created_at: datetime
    expires_at: datetime
    preview: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    approval_id: str
    status: ApprovalStatus
    decided_by: str | None
    decided_at: datetime | None
    reason: str | None = None


class ApprovalEngine(Protocol):
    def request(self, request: ApprovalRequest) -> Awaitable[ApprovalDecision]: ...

    def decide(
        self, approval_id: str, approved: bool, decided_by: str
    ) -> Awaitable[ApprovalDecision]: ...

    def get(self, approval_id: str) -> Awaitable[ApprovalDecision | None]: ...
