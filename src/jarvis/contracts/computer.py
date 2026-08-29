"""Computer-use actions remain behind a typed controller boundary."""

from __future__ import annotations

from collections.abc import Awaitable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from .tools import ToolContext, ToolResult


@dataclass(frozen=True, slots=True)
class ComputerAction:
    action: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    dry_run: bool = True


class ComputerCapability(StrEnum):
    OPEN_APPLICATION = "open_application"
    CLOSE_APPLICATION = "close_application"
    FOCUS_WINDOW = "focus_window"
    CHANGE_VOLUME = "change_volume"
    MUTE = "mute"
    UNMUTE = "unmute"
    LIST_PROCESSES = "list_processes"
    START_PROCESS = "start_process"
    STOP_SAFE_PROCESS = "stop_safe_process"
    INSPECT_FILE = "inspect_file"
    SEARCH_FILES = "search_files"
    OPEN_FILE = "open_file"
    OPEN_FOLDER = "open_folder"
    KEYBOARD_ACTION = "keyboard_action"
    MOUSE_ACTION = "mouse_action"
    WINDOW_ACTION = "window_action"
    CLIPBOARD_READ = "clipboard_read"
    CLIPBOARD_WRITE = "clipboard_write"
    SCREEN_SNAPSHOT_ON_DEMAND = "screen_snapshot_on_demand"


@dataclass(frozen=True, slots=True)
class ComputerResult:
    status: str
    output: Mapping[str, object] = field(default_factory=dict)
    error_code: str | None = None
    verified: bool = False
    approval_id: str | None = None


class ComputerController(Protocol):
    def execute(self, action: ComputerAction, context: ToolContext) -> Awaitable[ToolResult]: ...
