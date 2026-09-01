"""Product-owned contracts for governed MCP client integrations."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


_SCHEMA_KEYS = frozenset({
    "type", "properties", "required", "additionalProperties", "items", "enum",
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "minLength",
    "maxLength", "minItems", "maxItems", "pattern",
})
_SCHEMA_TYPES = frozenset({"object", "array", "string", "number", "integer", "boolean", "null"})
_SCHEMA_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]{0,63}\Z")
_SCHEMA_MAX_DEPTH = 8
_SCHEMA_MAX_PROPERTIES = 64
_SCHEMA_MAX_ENUM = 32
_SCHEMA_MAX_PATTERN = 256
_SCHEMA_MAX_BYTES = 16_384


def sanitize_input_schema(value: Mapping[str, object]) -> dict[str, object]:
    """Keep only bounded structural JSON-schema fields from an MCP server."""

    if not isinstance(value, Mapping):
        raise ValueError("mcp_tool_schema_must_be_object")
    normalized = _sanitize_schema_node(value, depth=0)
    if not normalized:
        normalized = {"type": "object", "additionalProperties": False}
    if "type" not in normalized and "properties" in normalized:
        normalized["type"] = "object"
    try:
        encoded = json.dumps(normalized, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("mcp_tool_schema_invalid") from exc
    if len(encoded) > _SCHEMA_MAX_BYTES:
        raise ValueError("mcp_tool_schema_too_large")
    return normalized


def _sanitize_schema_node(value: Mapping[str, object], *, depth: int) -> dict[str, object]:
    if depth > _SCHEMA_MAX_DEPTH:
        return {}
    result: dict[str, object] = {}
    raw_type = value.get("type")
    if isinstance(raw_type, str) and raw_type in _SCHEMA_TYPES:
        result["type"] = raw_type
    elif isinstance(raw_type, (list, tuple)):
        types = [item for item in raw_type if isinstance(item, str) and item in _SCHEMA_TYPES]
        if len(types) == 1:
            result["type"] = types[0]
    raw_properties = value.get("properties")
    if isinstance(raw_properties, Mapping):
        properties: dict[str, object] = {}
        for name, schema in list(raw_properties.items())[:_SCHEMA_MAX_PROPERTIES]:
            if not isinstance(name, str) or not _SCHEMA_NAME.fullmatch(name) or not isinstance(schema, Mapping):
                continue
            child = _sanitize_schema_node(schema, depth=depth + 1)
            if child:
                properties[name] = child
        if properties:
            result["properties"] = properties
    raw_required = value.get("required")
    if isinstance(raw_required, (list, tuple)) and isinstance(result.get("properties"), Mapping):
        properties = result["properties"]
        required = [item for item in raw_required[:_SCHEMA_MAX_PROPERTIES] if isinstance(item, str) and item in properties]
        if required:
            result["required"] = list(dict.fromkeys(required))
    additional = value.get("additionalProperties")
    if isinstance(additional, bool):
        result["additionalProperties"] = additional
    raw_items = value.get("items")
    if isinstance(raw_items, Mapping):
        items = _sanitize_schema_node(raw_items, depth=depth + 1)
        if items:
            result["items"] = items
    raw_enum = value.get("enum")
    if isinstance(raw_enum, (list, tuple)) and len(raw_enum) <= _SCHEMA_MAX_ENUM:
        enum: list[object] = []
        for item in raw_enum:
            if isinstance(item, (str, int, float, bool)) or item is None:
                if isinstance(item, str) and len(item) > 256:
                    continue
                if isinstance(item, float) and not math.isfinite(item):
                    continue
                enum.append(item)
        if enum:
            result["enum"] = enum
    for key in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"):
        bound = value.get(key)
        if isinstance(bound, (int, float)) and not isinstance(bound, bool) and math.isfinite(bound):
            result[key] = bound
    for key in ("minLength", "maxLength", "minItems", "maxItems"):
        bound = value.get(key)
        if isinstance(bound, int) and not isinstance(bound, bool) and 0 <= bound <= 1_000_000:
            result[key] = bound
    pattern = value.get("pattern")
    if isinstance(pattern, str) and len(pattern) <= _SCHEMA_MAX_PATTERN:
        try:
            re.compile(pattern)
        except re.error:
            pass
        else:
            result["pattern"] = pattern
    return {key: result[key] for key in _SCHEMA_KEYS if key in result}


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
        normalized_schema = sanitize_input_schema(self.input_schema)
        object.__setattr__(self, "input_schema", normalized_schema)
        try:
            size = len(json.dumps(normalized_schema, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
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
