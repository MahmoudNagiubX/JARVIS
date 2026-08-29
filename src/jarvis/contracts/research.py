"""Bounded, evidence-led research runtime contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ResearchRequest:
    query: str
    owner_id: str
    device_id: str
    max_steps: int = 8
    max_sources: int = 8
    max_seconds: float = 30.0
    context: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ResearchPlan:
    steps: tuple[str, ...]
    source_types: tuple[str, ...] = ("local", "browser")


@dataclass(frozen=True, slots=True)
class ResearchStep:
    step_id: str
    title: str
    status: str = "queued"
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class ResearchSource:
    source_id: str
    locator: str
    title: str
    source_type: str
    retrieved_at: datetime | None = None
    fingerprint: str | None = None
    trust: str = "unverified"


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    evidence_id: str
    source_id: str
    excerpt: str
    locator: str
    fingerprint: str
    untrusted_content: bool = True


@dataclass(frozen=True, slots=True)
class CitationRecord:
    citation_id: str
    evidence_id: str
    label: str
    valid: bool = True


@dataclass(frozen=True, slots=True)
class ResearchFinding:
    finding_id: str
    statement: str
    evidence_ids: tuple[str, ...] = ()
    confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class ResearchReport:
    title: str
    summary: str
    findings: tuple[ResearchFinding, ...] = ()
    citations: tuple[CitationRecord, ...] = ()
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ResearchRun:
    run_id: str
    request: ResearchRequest
    plan: ResearchPlan
    status: str = "queued"
    steps: tuple[ResearchStep, ...] = ()
    sources: tuple[ResearchSource, ...] = ()
    evidence: tuple[EvidenceItem, ...] = ()
    report: ResearchReport | None = None
    error_code: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None
