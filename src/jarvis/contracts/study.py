"""Bounded study and lecture workflow contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class StudyResolutionStatus(StrEnum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"
    NOT_CONFIGURED = "not_configured"


@dataclass(frozen=True, slots=True)
class StudyLectureCandidate:
    candidate_ref: str
    title: str
    kind: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class StudyResolution:
    resolution_id: str
    query: str
    status: StudyResolutionStatus
    candidates: tuple[StudyLectureCandidate, ...] = ()
    selected_ref: str | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class StudyStep:
    step_id: str
    kind: str
    title: str
    status: str
    target: str | None = None
    optional: bool = False


@dataclass(frozen=True, slots=True)
class StudyPlan:
    plan_id: str
    query: str
    status: str
    resolution: StudyResolution
    steps: tuple[StudyStep, ...] = field(default_factory=tuple)
    reason: str | None = None
