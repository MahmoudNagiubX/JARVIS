"""Small, deterministic UIA control-tree fakes shared by the Computer Use V2
evaluation suite (`computer_use_v2.py`). Mirrors the fakes already used in
`tests/test_phase_eighteen_semantic_uia.py` - kept intentionally minimal;
this module exists only so the evaluation suite (which must run without a
GUI/live Windows dependency) can exercise real `WindowsUIAutomationAdapter`
code against a fake control graph, not to duplicate the full unit-test
fixture surface.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from ..perception.privacy import PerceptionPrivacyPolicy


class FakeControl:
    def __init__(
        self,
        name: str | None,
        control_type: str,
        *,
        automation_id: str | None = None,
        enabled: bool = True,
        offscreen: bool = False,
        runtime_id: tuple[int, ...] = (1,),
        patterns: dict[int, object] | None = None,
        children: list["FakeControl"] | None = None,
    ) -> None:
        self.Name = name
        self.ControlTypeName = control_type
        self.AutomationId = automation_id
        self.IsEnabled = enabled
        self.IsOffscreen = offscreen
        self.HasKeyboardFocus = False
        self.IsKeyboardFocusable = True
        self.IsPassword = False
        self.BoundingRectangle = SimpleNamespace(left=0, top=0, right=10, bottom=10)
        self._runtime_id = runtime_id
        self._children = children or []
        self._patterns = patterns or {}

    def GetChildren(self) -> list["FakeControl"]:
        return list(self._children)

    def GetRuntimeId(self) -> list[int]:
        return list(self._runtime_id)

    def GetPattern(self, pattern_id: int) -> object | None:
        return self._patterns.get(pattern_id)


class FreezesAtFetchTogglePattern:
    """A TogglePattern whose `ToggleState` freezes at the moment it was
    fetched (mirrors a stale/re-marshalled COM wrapper), while `Toggle()`
    still mutates shared ground truth. Only passes a fresh-post-action-read
    contract if the caller genuinely calls `GetPattern()` again afterward
    rather than reusing the pre-action reference (R18B01-003)."""

    def __init__(self, box: dict[str, int]) -> None:
        self._box = box
        self._frozen = box["value"]

    @property
    def ToggleState(self) -> int:
        return self._frozen

    def Toggle(self) -> None:
        self._box["value"] = 1 if self._box["value"] == 0 else 0


class _MintingToggleControl(FakeControl):
    def __init__(self, box: dict[str, int], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._box = box

    def GetPattern(self, pattern_id: int) -> object | None:
        if pattern_id == 2:  # Toggle
            return FreezesAtFetchTogglePattern(self._box)
        return None


class FakeWindowProvider:
    def __init__(self, hwnd_by_ref: dict[str, int]) -> None:
        self._hwnd_by_ref = hwnd_by_ref
        self.privacy_policy = PerceptionPrivacyPolicy()

    def validate_input_window(self, window_ref: str) -> int:
        hwnd = self._hwnd_by_ref.get(window_ref)
        if hwnd is None:
            raise ValueError("window_ref_expired")
        return hwnd


def fake_control_tree(*, weak: bool, toggle_box: dict[str, int] | None = None) -> tuple[FakeControl, FakeWindowProvider, int]:
    """One window containing one Button (Invoke) and one CheckBox (Toggle),
    with strong or weak identity depending on `weak`."""

    class _FakeInvokePattern:
        def Invoke(self) -> None:
            pass

    button_runtime = () if weak else (1, 7)
    checkbox_runtime = () if weak else (1, 8)
    button = FakeControl(
        "Seven", "ButtonControl", automation_id="num7Button", runtime_id=button_runtime,
        patterns={1: _FakeInvokePattern()},
    )
    if toggle_box is not None:
        checkbox = _MintingToggleControl(
            toggle_box, name="Check", control_type="CheckBoxControl", automation_id="checkBox",
            runtime_id=checkbox_runtime,
        )
    else:
        checkbox = FakeControl("Check", "CheckBoxControl", automation_id="checkBox", runtime_id=checkbox_runtime)
    root = FakeControl("Win", "WindowControl", runtime_id=(1,) if not weak else (), children=[button, checkbox])
    provider = FakeWindowProvider({"window-1": 111})
    return root, provider, 111
