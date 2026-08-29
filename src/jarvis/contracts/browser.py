"""Browser-use actions remain behind a typed controller boundary."""

from __future__ import annotations

from collections.abc import Awaitable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from .tools import ToolContext, ToolResult


@dataclass(frozen=True, slots=True)
class BrowserAction:
    action: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    dry_run: bool = True


class BrowserController(Protocol):
    def execute(self, action: BrowserAction, context: ToolContext) -> Awaitable[ToolResult]: ...
