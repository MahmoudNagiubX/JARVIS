"""Bounded engineering-copilot contracts and injected provider boundary."""

from __future__ import annotations

from collections.abc import Awaitable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class EngineeringWorkspace:
    workspace_id: str
    root: str
    read_scope: tuple[str, ...] = ()
    write_scope: tuple[str, ...] = ()
    allowed_tools: frozenset[str] = field(default_factory=frozenset)
    timeout_seconds: float = 30.0
    risk: str = "read"
    approval_required: bool = True


@dataclass(frozen=True, slots=True)
class EngineeringSession:
    session_id: str
    owner_id: str
    device_id: str
    provider: str
    workspace: EngineeringWorkspace
    status: str = "active"
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class EngineeringArtifact:
    artifact_id: str
    kind: str
    name: str
    content_digest: str | None = None
    provenance: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EngineeringAction:
    session_id: str
    action: str
    target: str | None = None
    parameters: Mapping[str, object] = field(default_factory=dict)
    dry_run: bool = True
    action_id: str | None = None


@dataclass(frozen=True, slots=True)
class EngineeringResult:
    action_id: str
    status: str
    output: Any = None
    artifacts: tuple[EngineeringArtifact, ...] = ()
    error_code: str | None = None
    approval_id: str | None = None
    verified: bool = False


class EngineeringProvider(Protocol):
    name: str
    available: bool

    async def execute(self, action: EngineeringAction, workspace: EngineeringWorkspace) -> EngineeringResult: ...

    def capabilities(self) -> tuple[str, ...]: ...
