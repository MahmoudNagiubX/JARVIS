"""Static versioned capability catalog inspired by BMO Phase 08."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from ..contracts import ToolContext, ToolResult, ToolResultStatus

ToolHandler = Callable[[Mapping[str, Any], ToolContext], ToolResult | Awaitable[ToolResult]]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    tool_id: str
    name: str
    version: str
    description: str
    risk_level: str
    required_scope: str
    required_capabilities: frozenset[str]
    timeout_seconds: float
    idempotent: bool
    handler: ToolHandler
    requires_approval: bool = False
    enabled: bool = True

    def validate_arguments(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(arguments, Mapping):
            raise ValueError("arguments_must_be_object")
        normalized = dict(arguments)
        if any(token in key.casefold() for key in normalized for token in ("secret", "token", "password", "credential")):
            raise ValueError("sensitive_arguments_not_supported_in_phase02")
        if self.name.endswith("status.read") and normalized:
            raise ValueError("status_read_takes_no_arguments")
        if self.name.endswith("echo.reversible") or self.name.endswith("echo.consequential"):
            if not isinstance(normalized.get("message"), str) or not normalized["message"].strip():
                raise ValueError("message_required")
            if len(normalized["message"]) > 2000:
                raise ValueError("message_too_long")
        return normalized


class ToolRegistry:
    def __init__(self, specs: tuple[ToolSpec, ...] = ()) -> None:
        self._specs: dict[tuple[str, str], ToolSpec] = {}
        for spec in specs:
            self.register(spec)

    def register(self, spec: ToolSpec) -> None:
        key = (spec.name, spec.version)
        if key in self._specs:
            raise ValueError(f"duplicate tool: {spec.name}@{spec.version}")
        self._specs[key] = spec

    def get(self, name: str, version: str = "1") -> ToolSpec | None:
        return self._specs.get((name, version))

    def list(self) -> tuple[ToolSpec, ...]:
        return tuple(sorted(self._specs.values(), key=lambda spec: (spec.name, spec.version)))


def _status(_: Mapping[str, Any], __: ToolContext) -> ToolResult:
    return ToolResult(ToolResultStatus.SUCCEEDED, {"ok": True, "state": "ready"}, verified=True)


def _echo(arguments: Mapping[str, Any], __: ToolContext) -> ToolResult:
    return ToolResult(ToolResultStatus.SUCCEEDED, {"ok": True, "message": arguments["message"]}, verified=True)


def default_registry() -> ToolRegistry:
    return ToolRegistry(
        (
            ToolSpec(
                "tool-status-read-v1", "status.read", "1", "Read bounded JARVIS status.",
                "read", "tool.request", frozenset(), 5.0, True, _status,
            ),
            ToolSpec(
                "tool-echo-reversible-v1", "echo.reversible", "1", "Return a bounded reversible test value.",
                "reversible", "tool.request", frozenset(), 5.0, True, _echo,
            ),
            ToolSpec(
                "tool-echo-consequential-v1", "echo.consequential", "1", "Return a consequential approval fixture.",
                "consequential", "tool.request", frozenset(), 5.0, True, _echo, True,
            ),
        )
    )
