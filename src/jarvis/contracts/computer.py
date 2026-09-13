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
    SEMANTIC_LIST_WINDOWS = "semantic_list_windows"
    SEMANTIC_INSPECT_WINDOW = "semantic_inspect_window"
    SEMANTIC_FIND_ELEMENTS = "semantic_find_elements"
    SEMANTIC_GET_ELEMENT = "semantic_get_element"
    SEMANTIC_GET_TEXT = "semantic_get_text"
    SEMANTIC_REVALIDATE = "semantic_revalidate"
    SEMANTIC_INVOKE = "semantic_invoke"
    SEMANTIC_TOGGLE = "semantic_toggle"
    SEMANTIC_SELECT = "semantic_select"
    POINTER_MOVE_TO_ELEMENT = "pointer_move_to_element"
    POINTER_LEFT_CLICK_ELEMENT = "pointer_left_click_element"
    POINTER_RIGHT_CLICK_ELEMENT = "pointer_right_click_element"
    POINTER_DOUBLE_CLICK_ELEMENT = "pointer_double_click_element"
    POINTER_SCROLL_ELEMENT = "pointer_scroll_element"
    # Two-target action (Batch 04 Milestone 1) - deliberately not modeled as
    # an element-targeted single-ref action; see
    # ComputerActionService._dual_target_actions and _drag_target_preview.
    POINTER_DRAG_ELEMENT_TO_ELEMENT = "pointer_drag_element_to_element"
    KEYBOARD_KEY = "keyboard_key"
    KEYBOARD_CHORD = "keyboard_chord"
    # Internal-only capabilities: never registered in any ToolSpec, so the
    # model can never request them directly. ComputerActionService uses
    # these to build a fresh, trusted target preview/binding before creating
    # an approval for an element- or window-targeted action (R18B02-001/003).
    RESOLVE_ELEMENT_TARGET = "resolve_element_target"
    RESOLVE_WINDOW_TARGET = "resolve_window_target"


@dataclass(frozen=True, slots=True)
class ComputerResult:
    status: str
    output: Mapping[str, object] = field(default_factory=dict)
    error_code: str | None = None
    verified: bool = False
    approval_id: str | None = None


class ComputerController(Protocol):
    def execute(self, action: ComputerAction, context: ToolContext) -> Awaitable[ToolResult]: ...
