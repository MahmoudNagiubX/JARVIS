"""Tool execution contracts and the product-owned capability registry."""

from __future__ import annotations

from collections.abc import Awaitable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from .identity import DeviceIdentity, Identity


class ToolResultStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DENIED = "denied"
    CANCELLED = "cancelled"


class ToolResultRetention(StrEnum):
    DURABLE = "durable"
    EPHEMERAL = "ephemeral"


@dataclass(frozen=True, slots=True)
class ToolContext:
    identity: Identity | None
    device: DeviceIdentity | None
    session_id: str
    correlation_id: str
    deadline_at: datetime | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ToolResult:
    status: ToolResultStatus
    output: Any = None
    error_code: str | None = None
    verified: bool = False


class Tool(Protocol):
    name: str
    version: str
    description: str

    def execute(self, arguments: Mapping[str, Any], context: ToolContext) -> Awaitable[ToolResult]: ...


class ToolRegistry(Protocol):
    def register(self, tool: Tool) -> None: ...

    def get(self, name: str, version: str | None = None) -> Tool | None: ...

    def list(self) -> tuple[Tool, ...]: ...
