"""Declarative, product-owned skill contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class SkillStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class SkillStep:
    step_id: str
    title: str
    action: str
    arguments: Mapping[str, object] = field(default_factory=dict)
    required_capabilities: tuple[str, ...] = ()
    risk_level: str = "read"
    requires_approval: bool = False


@dataclass(frozen=True, slots=True)
class SkillManifest:
    skill_id: str
    name: str
    description: str
    version: str = "1.0.0"
    category: str = "general"
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    required_capabilities: tuple[str, ...] = ()
    risk_level: str = "read"
    autonomy_level: int = 0
    estimated_duration: float = 30.0
    workspace_scope: str | None = None
    network_requirement: str = "none"
    owner: str = "jarvis"
    status: SkillStatus = SkillStatus.ACTIVE


@dataclass(frozen=True, slots=True)
class Skill:
    manifest: SkillManifest
    steps: tuple[SkillStep, ...] = ()
    instructions_path: str | None = None
    instructions: str | None = None


@dataclass(frozen=True, slots=True)
class SkillInput:
    values: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SkillOutput:
    skill_id: str
    status: str
    results: tuple[Mapping[str, object], ...] = ()
    error_code: str | None = None
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SkillVersion:
    version_id: str
    skill_id: str
    version: str
    manifest: SkillManifest
    source: str
    change_reason: str
    previous_version: str | None = None
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SkillDraft:
    draft_id: str
    skill: Skill
    source_workflow: str
    safety_notes: tuple[str, ...] = ()
    created_at: datetime | None = None
