"""Product-owned, vendor-neutral semantic desktop UI (Windows UIA) contracts.

These are the only shapes a semantic desktop adapter (see
`src/jarvis/computer/semantic_uia.py`) may return. No raw COM object,
RuntimeId, HWND, or coordinate is ever a target identity here - opaque,
JARVIS-issued, ephemeral references are the only way to address a window
or element across calls.
"""

from __future__ import annotations

from collections.abc import Awaitable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol


class SemanticReferenceState(StrEnum):
    VALID = "valid"
    STALE = "stale"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"
    SENSITIVE_DENIED = "sensitive_denied"
    PROVIDER_UNAVAILABLE = "provider_unavailable"


@dataclass(frozen=True, slots=True)
class SemanticBounds:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class SemanticElementSnapshot:
    element_ref: str
    window_ref: str
    name: str | None
    control_type: str
    automation_id: str | None
    enabled: bool
    offscreen: bool
    focused: bool
    focusable: bool
    bounds: SemanticBounds | None
    supported_patterns: tuple[str, ...] = ()
    text: str | None = None
    observed_at: datetime | None = None
    # True only when this reference carries a strong (non-empty RuntimeId) identity
    # AND is enabled/onscreen/non-password at observation time - the model may rely
    # on this to know whether invoke/toggle/select would even be attempted; it never
    # exposes *why* in provider terms (no RuntimeId/digest is ever surfaced).
    actionable: bool = True


@dataclass(frozen=True, slots=True)
class SemanticTreeNode:
    """One bounded element snapshot plus its already-walked children."""

    snapshot: SemanticElementSnapshot
    children: tuple["SemanticTreeNode", ...] = ()


@dataclass(frozen=True, slots=True)
class SemanticResult:
    """One typed envelope for every semantic read operation, mirroring the
    existing ComputerResult/HomeResult/BrowserResult status+output+error_code
    convention used throughout the codebase."""

    status: str
    output: Mapping[str, object] = field(default_factory=dict)
    error_code: str | None = None


class SemanticDesktopAdapter(Protocol):
    """Product-owned semantic desktop boundary. Exactly one implementation
    may be wired into the runtime at a time (see AGENTS.md single-authority
    rule) - this Protocol exists for testability/mockability, not to invite
    a second concrete provider family."""

    def list_windows(self, device_id: str) -> Awaitable[SemanticResult]: ...

    def inspect_window(self, window_ref: str, *, depth: int) -> Awaitable[SemanticResult]: ...

    def find_elements(
        self,
        window_ref: str,
        *,
        control_type: str | None = None,
        name: str | None = None,
        automation_id: str | None = None,
    ) -> Awaitable[SemanticResult]: ...

    def get_element(self, element_ref: str) -> Awaitable[SemanticResult]: ...

    def resolve_actionable_target(self, element_ref: str) -> Awaitable[SemanticResult]: ...

    def get_text_or_value(self, element_ref: str) -> Awaitable[SemanticResult]: ...

    def revalidate_reference(self, element_ref: str) -> Awaitable[SemanticResult]: ...

    def invoke(self, element_ref: str) -> Awaitable[SemanticResult]: ...

    def toggle(self, element_ref: str) -> Awaitable[SemanticResult]: ...

    def select(self, element_ref: str) -> Awaitable[SemanticResult]: ...
