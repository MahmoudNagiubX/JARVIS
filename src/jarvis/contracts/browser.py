"""Browser-use actions remain behind a typed controller boundary."""

from __future__ import annotations

from collections.abc import Awaitable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from .tools import ToolContext, ToolResult


@dataclass(frozen=True, slots=True)
class BrowserAction:
    action: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    dry_run: bool = True


class BrowserCapability(StrEnum):
    OPEN_URL = "open_url"
    NAVIGATE = "navigate"
    BACK = "back"
    FORWARD = "forward"
    READ_PAGE = "read_page"
    INSPECT_ACCESSIBILITY_TREE = "inspect_accessibility_tree"
    FIND_ELEMENT = "find_element"
    CLICK = "click"
    TYPE = "type"
    SELECT = "select"
    EXTRACT_TEXT = "extract_text"
    DOWNLOAD_FILE = "download_file"
    UPLOAD_FILE = "upload_file"
    TABS = "tabs"
    SCREENSHOT = "screenshot"


class BrowserSessionMode(StrEnum):
    """Product-owned browser lifetime modes; never model-controlled."""

    EPHEMERAL = "ephemeral"
    OWNER_PERSISTENT = "owner_persistent"


@dataclass(frozen=True, slots=True)
class BrowserSession:
    session_id: str
    owner_id: str
    device_id: str
    current_url: str | None = None
    history: tuple[str, ...] = ()
    active: bool = True
    mode: BrowserSessionMode = BrowserSessionMode.EPHEMERAL


@dataclass(frozen=True, slots=True)
class BrowserResult:
    status: str
    output: Mapping[str, object] = field(default_factory=dict)
    error_code: str | None = None
    verified: bool = False
    approval_id: str | None = None


class BrowserController(Protocol):
    def execute(
        self,
        action: BrowserAction,
        context: ToolContext,
        *,
        session_mode: BrowserSessionMode = BrowserSessionMode.EPHEMERAL,
    ) -> Awaitable[ToolResult]: ...

    def close(self) -> Awaitable[None]: ...
