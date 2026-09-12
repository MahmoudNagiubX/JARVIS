"""Product-owned semantic Windows UI Automation adapter (Computer Use V2, Layer 1).

Wraps the optional `uiautomation` (+ `comtypes`) dependency behind one typed,
vendor-neutral boundary (DEC-046). No raw COM object, RuntimeId, HWND, or
coordinate ever crosses out of this module as a target identity - only
opaque, ephemeral, TTL-bound `element-<uuid>` references and the normalized
`SemanticElementSnapshot`/`SemanticResult` contracts in
`..contracts.semantic_ui` do.

Stale-target safety by construction: no live `uiautomation` Control object
is ever held across two calls. Every re-resolution (`get_element`,
`get_text_or_value`, `revalidate_reference`, and pattern actuation in a
later milestone) re-walks the bounded tree from the containing window and
accepts a match only when its live RuntimeId digest equals the digest
captured at observation time - a same-named element with a different
identity is never silently substituted.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from ..contracts.semantic_ui import (
    SemanticBounds,
    SemanticElementSnapshot,
    SemanticReferenceState,
    SemanticResult,
    SemanticTreeNode,
)
from ..perception.privacy import PerceptionPrivacyPolicy
from ..perception.windows import WindowsDesktopProvider

try:
    import uiautomation as _uia
except ImportError:  # pragma: no cover - exercised via the dependency-unavailable tests
    _uia = None


DEFAULT_INSPECT_DEPTH = 3
MAX_INSPECT_DEPTH = 5
MAX_TREE_ELEMENTS = 200
MAX_FIND_RESULTS = 50
MAX_ANCESTRY_HINTS = 6
MAX_TEXT_LENGTH = 4_000
ELEMENT_REF_TTL_SECONDS = 45
MAX_ELEMENT_REFS = 1_000

_WINDOW_ERROR_TRANSLATION = {
    "sensitive_window_denied": "sensitive_window_denied",
    "window_ref_required": "uia_window_stale",
    "window_ref_expired": "uia_window_stale",
    "window_ref_changed": "uia_window_stale",
}

_REVALIDATION_STATE = {
    "uia_element_not_found": SemanticReferenceState.NOT_FOUND,
    "uia_element_stale": SemanticReferenceState.STALE,
    "uia_element_ambiguous": SemanticReferenceState.AMBIGUOUS,
    "uia_window_stale": SemanticReferenceState.STALE,
    "sensitive_window_denied": SemanticReferenceState.SENSITIVE_DENIED,
    "uia_not_available": SemanticReferenceState.PROVIDER_UNAVAILABLE,
    "uia_provider_unavailable": SemanticReferenceState.PROVIDER_UNAVAILABLE,
}


@dataclass(slots=True)
class _ElementRefEntry:
    """Provider-private identity/re-resolution hints. Never exposed to the model."""

    window_ref: str
    automation_id: str | None
    control_type: str
    name_hint: str | None
    ancestry_hint: tuple[str, ...]
    runtime_id_digest: str
    expires_at: datetime


def _real_pattern_ids() -> dict[str, int]:
    return {
        "Invoke": _uia.PatternId.InvokePattern,
        "Toggle": _uia.PatternId.TogglePattern,
        "SelectionItem": _uia.PatternId.SelectionItemPattern,
        "Value": _uia.PatternId.ValuePattern,
        "Text": _uia.PatternId.TextPattern,
    }


def _safe_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value[:300]
    return None


def _safe_bounds(control: Any) -> SemanticBounds | None:
    rect = getattr(control, "BoundingRectangle", None)
    left = getattr(rect, "left", None)
    top = getattr(rect, "top", None)
    right = getattr(rect, "right", None)
    bottom = getattr(rect, "bottom", None)
    if None in (left, top, right, bottom):
        return None
    width, height = right - left, bottom - top
    if width <= 0 or height <= 0:
        return None
    return SemanticBounds(int(left), int(top), int(width), int(height))


def _runtime_id_digest(control: Any) -> str:
    getter = getattr(control, "GetRuntimeId", None)
    try:
        runtime_id = tuple(getter()) if getter is not None else ()
    except Exception:
        runtime_id = ()
    return hashlib.sha256(repr(runtime_id).encode("utf-8")).hexdigest()


class WindowsUIAutomationAdapter:
    """Semantic desktop adapter backed by `uiautomation`/`comtypes`, behind one boundary.

    Reuses the existing `WindowsDesktopProvider` as the sole authority for
    opaque top-level window references (TTL, staleness, privacy) - this
    adapter never issues a parallel window-reference scheme, only its own
    ephemeral element references tied to an existing `window_ref`.
    """

    name = "windows-uiautomation"

    def __init__(
        self,
        window_provider: WindowsDesktopProvider,
        *,
        privacy_policy: PerceptionPrivacyPolicy | None = None,
        element_ref_ttl_seconds: int = ELEMENT_REF_TTL_SECONDS,
        control_from_handle: Any = None,
        pattern_ids: dict[str, int] | None = None,
    ) -> None:
        self.window_provider = window_provider
        self.privacy_policy = privacy_policy or getattr(window_provider, "privacy_policy", None) or PerceptionPrivacyPolicy()
        self.element_ref_ttl_seconds = max(15, min(60, element_ref_ttl_seconds))
        self._element_refs: dict[str, _ElementRefEntry] = {}
        # Both are injectable so unit tests can exercise the real tree-walk/staleness
        # logic deterministically with a fake control graph, without requiring the
        # real `uiautomation` package (or a GUI session) to be present in CI.
        if control_from_handle is not None:
            self._control_from_handle = control_from_handle
            self._pattern_ids = pattern_ids or {}
            self.available = True
        elif _uia is not None:
            self._control_from_handle = _uia.ControlFromHandle
            self._pattern_ids = _real_pattern_ids()
            self.available = True
        else:
            self._control_from_handle = None
            self._pattern_ids = {}
            self.available = False

    def capabilities(self) -> dict[str, object]:
        return {"available": self.available, "reason": None if self.available else "uia_not_available"}

    async def list_windows(self, device_id: str) -> SemanticResult:
        if not self.available:
            return SemanticResult("failed", error_code="uia_not_available")
        context = self.window_provider.desktop_context(device_id)
        return SemanticResult("succeeded", {"windows": context.windows})

    async def inspect_window(self, window_ref: str, *, depth: int = DEFAULT_INSPECT_DEPTH) -> SemanticResult:
        if not self.available:
            return SemanticResult("failed", error_code="uia_not_available")
        bounded_depth = max(1, min(depth, MAX_INSPECT_DEPTH))
        root, error = self._resolve_window_root(window_ref)
        if root is None:
            return SemanticResult("failed" if error != "sensitive_window_denied" else "denied", error_code=error)
        now = datetime.now(UTC)
        state = {"count": 0, "truncated": False}

        def build(control: Any, ancestry: tuple[str, ...], depth_remaining: int) -> SemanticTreeNode | None:
            if state["count"] >= MAX_TREE_ELEMENTS:
                state["truncated"] = True
                return None
            state["count"] += 1
            snapshot, entry = self._make_snapshot(control, window_ref, ancestry, now)
            self._store_ref(snapshot.element_ref, entry)
            children: list[SemanticTreeNode] = []
            if depth_remaining > 0:
                for child in self._children_of(control):
                    if state["count"] >= MAX_TREE_ELEMENTS:
                        state["truncated"] = True
                        break
                    node = build(child, (ancestry + (snapshot.control_type,))[-MAX_ANCESTRY_HINTS:], depth_remaining - 1)
                    if node is not None:
                        children.append(node)
            return SemanticTreeNode(snapshot, tuple(children))

        tree = build(root, (), bounded_depth)
        return SemanticResult("succeeded", {"tree": tree, "element_count": state["count"], "truncated": state["truncated"]})

    async def find_elements(
        self,
        window_ref: str,
        *,
        control_type: str | None = None,
        name: str | None = None,
        automation_id: str | None = None,
    ) -> SemanticResult:
        if not self.available:
            return SemanticResult("failed", error_code="uia_not_available")
        if control_type is None and name is None and automation_id is None:
            return SemanticResult("denied", error_code="uia_find_filter_required")
        root, error = self._resolve_window_root(window_ref)
        if root is None:
            return SemanticResult("failed" if error != "sensitive_window_denied" else "denied", error_code=error)
        now = datetime.now(UTC)
        matches: list[SemanticElementSnapshot] = []
        for control, ancestry, _depth in self._walk(root, MAX_INSPECT_DEPTH, MAX_TREE_ELEMENTS):
            if control_type is not None and _safe_str(getattr(control, "ControlTypeName", None)) != control_type:
                continue
            if automation_id is not None and _safe_str(getattr(control, "AutomationId", None)) != automation_id:
                continue
            if name is not None and (getattr(control, "Name", None) or None) != name:
                continue
            snapshot, entry = self._make_snapshot(control, window_ref, ancestry, now)
            self._store_ref(snapshot.element_ref, entry)
            matches.append(snapshot)
            if len(matches) >= MAX_FIND_RESULTS:
                break
        return SemanticResult("succeeded", {"matches": tuple(matches), "ambiguous": len(matches) > 1})

    async def get_element(self, element_ref: str) -> SemanticResult:
        if not self.available:
            return SemanticResult("failed", error_code="uia_not_available")
        control, entry, ancestry, error = self._reresolve(element_ref)
        if control is None:
            return SemanticResult("failed" if error != "sensitive_window_denied" else "denied", error_code=error)
        now = datetime.now(UTC)
        snapshot, new_entry = self._make_snapshot(control, entry.window_ref, ancestry, now, element_ref=element_ref)
        self._element_refs[element_ref] = new_entry
        return SemanticResult("succeeded", {"element": snapshot})

    async def get_text_or_value(self, element_ref: str) -> SemanticResult:
        if not self.available:
            return SemanticResult("failed", error_code="uia_not_available")
        control, entry, ancestry, error = self._reresolve(element_ref)
        if control is None:
            return SemanticResult("failed" if error != "sensitive_window_denied" else "denied", error_code=error)
        if bool(getattr(control, "IsPassword", False)):
            return SemanticResult("denied", error_code="uia_sensitive_value_denied")
        now = datetime.now(UTC)
        _snapshot, new_entry = self._make_snapshot(control, entry.window_ref, ancestry, now, element_ref=element_ref)
        self._element_refs[element_ref] = new_entry
        text = self._read_text(control)
        truncated = False
        if isinstance(text, str) and len(text) > MAX_TEXT_LENGTH:
            text = text[:MAX_TEXT_LENGTH]
            truncated = True
        return SemanticResult("succeeded", {"text": text, "truncated": truncated})

    async def revalidate_reference(self, element_ref: str) -> SemanticResult:
        if not self.available:
            return SemanticResult(
                "failed", {"state": SemanticReferenceState.PROVIDER_UNAVAILABLE.value}, "uia_not_available"
            )
        control, entry, ancestry, error = self._reresolve(element_ref)
        if control is None:
            state = _REVALIDATION_STATE.get(error, SemanticReferenceState.NOT_FOUND)
            status = "denied" if state is SemanticReferenceState.SENSITIVE_DENIED else "failed"
            return SemanticResult(status, {"state": state.value}, error)
        now = datetime.now(UTC)
        snapshot, new_entry = self._make_snapshot(control, entry.window_ref, ancestry, now, element_ref=element_ref)
        self._element_refs[element_ref] = new_entry
        return SemanticResult("succeeded", {"state": SemanticReferenceState.VALID.value, "element": snapshot})

    # -- internal boundary: nothing below this line returns a raw provider object --

    def _resolve_window_root(self, window_ref: str) -> tuple[Any, str]:
        try:
            hwnd = self.window_provider.validate_input_window(window_ref)
        except ValueError as exc:
            return None, _WINDOW_ERROR_TRANSLATION.get(str(exc), "uia_window_stale")
        try:
            control = self._control_from_handle(hwnd)
        except Exception:
            return None, "uia_provider_unavailable"
        if control is None:
            return None, "uia_provider_unavailable"
        return control, ""

    def _children_of(self, control: Any) -> list[Any]:
        try:
            return list(control.GetChildren())
        except Exception:
            return []

    def _walk(self, root: Any, max_depth: int, max_count: int) -> Iterator[tuple[Any, tuple[str, ...], int]]:
        state = {"count": 0}

        def rec(control: Any, ancestry: tuple[str, ...], depth: int) -> Iterator[tuple[Any, tuple[str, ...], int]]:
            if state["count"] >= max_count:
                return
            state["count"] += 1
            yield control, ancestry, depth
            if depth >= max_depth:
                return
            control_type = _safe_str(getattr(control, "ControlTypeName", None)) or "UnknownControl"
            child_ancestry = (ancestry + (control_type,))[-MAX_ANCESTRY_HINTS:]
            for child in self._children_of(control):
                if state["count"] >= max_count:
                    return
                yield from rec(child, child_ancestry, depth + 1)

        yield from rec(root, (), 0)

    def _reresolve(self, element_ref: str) -> tuple[Any, _ElementRefEntry | None, tuple[str, ...], str]:
        entry = self._element_refs.get(element_ref)
        if entry is None:
            return None, None, (), "uia_element_not_found"
        if entry.expires_at <= datetime.now(UTC):
            self._element_refs.pop(element_ref, None)
            return None, None, (), "uia_element_stale"
        root, error = self._resolve_window_root(entry.window_ref)
        if root is None:
            return None, entry, (), error or "uia_window_stale"
        candidates: list[tuple[Any, tuple[str, ...]]] = []
        for control, ancestry, _depth in self._walk(root, MAX_INSPECT_DEPTH, MAX_TREE_ELEMENTS):
            if _runtime_id_digest(control) == entry.runtime_id_digest:
                candidates.append((control, ancestry))
        if not candidates:
            # A live element with a matching identity digest no longer exists in the
            # bounded tree. Never substitute a same-named-but-different element.
            self._element_refs.pop(element_ref, None)
            return None, entry, (), "uia_element_stale"
        if len(candidates) > 1:
            return None, entry, (), "uia_element_ambiguous"
        control, ancestry = candidates[0]
        return control, entry, ancestry, ""

    def _make_snapshot(
        self,
        control: Any,
        window_ref: str,
        ancestry: tuple[str, ...],
        now: datetime,
        *,
        element_ref: str | None = None,
    ) -> tuple[SemanticElementSnapshot, _ElementRefEntry]:
        ref = element_ref or f"element-{uuid4()}"
        name = _safe_str(getattr(control, "Name", None))
        control_type = _safe_str(getattr(control, "ControlTypeName", None)) or "UnknownControl"
        automation_id = _safe_str(getattr(control, "AutomationId", None))
        enabled = bool(getattr(control, "IsEnabled", False))
        offscreen = bool(getattr(control, "IsOffscreen", False))
        focused = bool(getattr(control, "HasKeyboardFocus", False))
        focusable = bool(getattr(control, "IsKeyboardFocusable", False))
        bounds = _safe_bounds(control)
        patterns = tuple(sorted(pattern_name for pattern_name, pattern_id in self._pattern_ids.items() if self._has_pattern(control, pattern_id)))
        snapshot = SemanticElementSnapshot(
            ref, window_ref, name, control_type, automation_id,
            enabled, offscreen, focused, focusable, bounds, patterns, None, now,
        )
        entry = _ElementRefEntry(
            window_ref, automation_id, control_type, name,
            ancestry[-MAX_ANCESTRY_HINTS:] if ancestry else (),
            _runtime_id_digest(control),
            now + timedelta(seconds=self.element_ref_ttl_seconds),
        )
        return snapshot, entry

    @staticmethod
    def _has_pattern(control: Any, pattern_id: int) -> bool:
        try:
            return control.GetPattern(pattern_id) is not None
        except Exception:
            return False

    def _read_text(self, control: Any) -> str | None:
        text_pattern_id = self._pattern_ids.get("Text")
        if text_pattern_id is not None:
            try:
                text_pattern = control.GetPattern(text_pattern_id)
                if text_pattern is not None:
                    text = text_pattern.DocumentRange.GetText(-1)
                    if isinstance(text, str):
                        return text
            except Exception:
                pass
        value_pattern_id = self._pattern_ids.get("Value")
        if value_pattern_id is not None:
            try:
                value_pattern = control.GetPattern(value_pattern_id)
                if value_pattern is not None and isinstance(value_pattern.Value, str):
                    return value_pattern.Value
            except Exception:
                pass
        name = getattr(control, "Name", None)
        return name if isinstance(name, str) else None

    def _store_ref(self, element_ref: str, entry: _ElementRefEntry) -> None:
        self._prune_refs()
        while len(self._element_refs) >= MAX_ELEMENT_REFS:
            self._element_refs.pop(next(iter(self._element_refs)))
        self._element_refs[element_ref] = entry

    def _prune_refs(self, now: datetime | None = None) -> None:
        current = now or datetime.now(UTC)
        for ref, entry in tuple(self._element_refs.items()):
            if entry.expires_at <= current:
                self._element_refs.pop(ref, None)
