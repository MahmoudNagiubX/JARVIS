"""Computer-use actions remain behind a typed controller boundary."""

from __future__ import annotations

from collections.abc import Awaitable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from .tools import ToolContext, ToolResult


@dataclass(frozen=True, slots=True)
class ComputerAction:
    action: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    dry_run: bool = True


class ComputerController(Protocol):
    def execute(self, action: ComputerAction, context: ToolContext) -> Awaitable[ToolResult]: ...
