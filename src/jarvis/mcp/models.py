"""Product-owned contracts for governed MCP client integrations."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class MCPRisk(StrEnum):
    READ_ONLY = "read_only"
    REVERSIBLE = "reversible"
    CONSEQUENTIAL = "consequential"
    DANGEROUS = "dangerous"


class MCPServerState(StrEnum):
    DISABLED = "disabled"
    STOPPED = "stopped"
    STARTING = "starting"
    READY = "ready"
    DEGRADED = "degraded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class MCPServerConfig:
    server_id: str
    display_name: str
    command: str
    args: tuple[str, ...] = ()
    environment_allowlist: tuple[str, ...] = ()
    working_directory: str | None = None
    enabled: bool = True
    trust_level: str = "local"
    capability_allowlist: tuple[str, ...] = ()
    startup_timeout_seconds: float = 5.0
    execution_timeout_seconds: float = 30.0
    max_request_bytes: int = 64_000
    max_response_bytes: int = 1_000_000
    max_concurrent_calls: int = 4
    environment: Mapping[str, str] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", self.server_id):
            raise ValueError("invalid_mcp_server_id")
        if not self.display_name.strip() or not self.command.strip():
            raise ValueError("mcp_server_identity_required")
        process_values = (self.command, *self.args) + ((self.working_directory,) if self.working_directory else ())
        for value in process_values:
            if "\x00" in value or "\r" in value or "\n" in value:
                raise ValueError("mcp_process_value_invalid")
        for name in self.environment_allowlist:
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", name):
                raise ValueError("mcp_environment_name_invalid")
        if any(name not in self.environment_allowlist for name in self.environment):
            raise ValueError("mcp_environment_not_allowlisted")
        if any(not isinstance(value, str) or len(value) > 8_192 for value in self.environment.values()):
            raise ValueError("mcp_environment_value_invalid")
        if not 0.05 <= self.startup_timeout_seconds <= 120:
            raise ValueError("mcp_startup_timeout_out_of_bounds")
        if not 0.05 <= self.execution_timeout_seconds <= 300:
            raise ValueError("mcp_execution_timeout_out_of_bounds")
        if not 1_024 <= self.max_request_bytes <= 2_000_000:
            raise ValueError("mcp_request_bound_out_of_bounds")
        if not 1_024 <= self.max_response_bytes <= 8_000_000:
            raise ValueError("mcp_response_bound_out_of_bounds")
        if not 1 <= self.max_concurrent_calls <= 32:
            raise ValueError("mcp_concurrency_out_of_bounds")


@dataclass(frozen=True, slots=True)
class MCPDiscoveredTool:
    server_id: str
    name: str
    description: str
    input_schema: Mapping[str, object]
    risk_hint: MCPRisk | None = None
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.server_id.strip() or not self.name.strip():
            raise ValueError("mcp_tool_identity_required")
        if len(self.name) > 200 or len(self.description) > 2_000:
            raise ValueError("mcp_tool_metadata_too_large")
        if not isinstance(self.input_schema, Mapping):
            raise ValueError("mcp_tool_schema_must_be_object")
        try:
            size = len(json.dumps(self.input_schema, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        except (TypeError, ValueError) as exc:
            raise ValueError("mcp_tool_schema_invalid") from exc
        if size > 16_384:
            raise ValueError("mcp_tool_schema_too_large")


@dataclass(frozen=True, slots=True)
class MCPServerHealth:
    server_id: str
    state: MCPServerState = MCPServerState.STOPPED
    tool_count: int = 0
    last_error: str | None = None
    checked_at: datetime | None = None
    restart_count: int = 0

    @classmethod
    def initial(cls, server_id: str, enabled: bool) -> "MCPServerHealth":
        return cls(server_id, MCPServerState.STOPPED if enabled else MCPServerState.DISABLED)


@dataclass(frozen=True, slots=True)
class MCPPolicyDecision:
    risk: MCPRisk
    tool_risk_level: str
    requires_approval: bool
    autonomy_level: int


def now_utc() -> datetime:
    return datetime.now(UTC)
