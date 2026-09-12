"""Milestone 1 (Phase 18 Workstream A, Batch 01): semantic UIA foundation.

All tests use a fake/mock provider seam - no real `uiautomation` package,
GUI session, or Windows platform is required for this file to run
deterministically in CI. The one live-dependency-unavailable test patches
the module's optional import directly.
"""

from __future__ import annotations

import dataclasses
import unittest
import unittest.mock
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from jarvis.computer import semantic_uia
from jarvis.computer.semantic_uia import WindowsUIAutomationAdapter
from jarvis.contracts import DesktopContextSnapshot, DesktopWindow, VisualRegion
from jarvis.contracts.semantic_ui import SemanticElementSnapshot
from jarvis.perception.privacy import PerceptionPrivacyPolicy

PATTERN_IDS = {"Invoke": 1, "Toggle": 2, "SelectionItem": 3, "Value": 4, "Text": 5}


class _FakeTextPattern:
    def __init__(self, text: str) -> None:
        self._text = text
        self.DocumentRange = self

    def GetText(self, _max_length: int) -> str:
        return self._text


class _FakeValuePattern:
    def __init__(self, value: str) -> None:
        self.Value = value


class _FakeInvokePattern:
    def __init__(self) -> None:
        self.invoked = False

    def Invoke(self) -> None:
        self.invoked = True


class _FakeTogglePattern:
    def __init__(self, initial_state: int = 0, *, stuck: bool = False) -> None:
        self.ToggleState = initial_state
        self._stuck = stuck

    def Toggle(self) -> None:
        if not self._stuck:
            self.ToggleState = 1 if self.ToggleState == 0 else 0


class _FakeSelectionItemPattern:
    def __init__(self, *, stuck: bool = False) -> None:
        self.IsSelected = False
        self._stuck = stuck

    def Select(self) -> None:
        if not self._stuck:
            self.IsSelected = True


class _FakeControl:
    def __init__(
        self,
        name: str | None,
        control_type: str,
        *,
        automation_id: str | None = None,
        enabled: bool = True,
        offscreen: bool = False,
        focused: bool = False,
        focusable: bool = True,
        bounds: tuple[int, int, int, int] = (0, 0, 10, 10),
        runtime_id: tuple[int, ...] = (0,),
        patterns: dict[int, object] | None = None,
        is_password: bool = False,
        children: list["_FakeControl"] | None = None,
    ) -> None:
        self.Name = name
        self.ControlTypeName = control_type
        self.AutomationId = automation_id
        self.IsEnabled = enabled
        self.IsOffscreen = offscreen
        self.HasKeyboardFocus = focused
        self.IsKeyboardFocusable = focusable
        self.IsPassword = is_password
        left, top, right, bottom = bounds
        self.BoundingRectangle = SimpleNamespace(left=left, top=top, right=right, bottom=bottom)
        self._runtime_id = runtime_id
        self._children = children or []
        self._patterns = patterns or {}

    def GetChildren(self) -> list["_FakeControl"]:
        return list(self._children)

    def GetRuntimeId(self) -> list[int]:
        return list(self._runtime_id)

    def GetPattern(self, pattern_id: int) -> object | None:
        return self._patterns.get(pattern_id)


class _FakeWindowProvider:
    """Duck-typed stand-in for WindowsDesktopProvider - no real Windows needed."""

    def __init__(self, hwnd_by_ref: dict[str, int], *, deny_refs: frozenset[str] = frozenset()) -> None:
        self._hwnd_by_ref = hwnd_by_ref
        self._deny_refs = deny_refs
        self.privacy_policy = PerceptionPrivacyPolicy()

    def validate_input_window(self, window_ref: str) -> int:
        if window_ref in self._deny_refs:
            raise ValueError("sensitive_window_denied")
        hwnd = self._hwnd_by_ref.get(window_ref)
        if hwnd is None:
            raise ValueError("window_ref_expired")
        return hwnd

    def desktop_context(self, device_id: str) -> DesktopContextSnapshot:
        windows = tuple(
            DesktopWindow(ref, f"Window {ref}", "fake.exe", hwnd, "FakeClass", VisualRegion(0, 0, 100, 100), True, False)
            for ref, hwnd in self._hwnd_by_ref.items()
        )
        return DesktopContextSnapshot("snapshot-fake", device_id, datetime.now(UTC), None, windows, 1920, 1080, "fake", 1.0)


def _adapter(hwnd_by_control: dict[int, _FakeControl], window_provider: _FakeWindowProvider) -> WindowsUIAutomationAdapter:
    return WindowsUIAutomationAdapter(
        window_provider,  # type: ignore[arg-type]
        control_from_handle=lambda hwnd: hwnd_by_control.get(hwnd),
        pattern_ids=PATTERN_IDS,
    )


class SemanticUIAFoundationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.seven = _FakeControl(
            "Seven", "ButtonControl", automation_id="num7Button", runtime_id=(1, 7),
            patterns={PATTERN_IDS["Invoke"]: object()},
        )
        self.eight = _FakeControl("Eight", "ButtonControl", automation_id="num8Button", runtime_id=(1, 8))
        self.group = _FakeControl("Numbers", "GroupControl", runtime_id=(1, 0), children=[self.seven, self.eight])
        self.root = _FakeControl("Calculator", "WindowControl", runtime_id=(1,), children=[self.group])
        self.provider = _FakeWindowProvider({"window-1": 111})
        self.adapter = _adapter({111: self.root}, self.provider)

    # -- dependency availability --

    async def test_dependency_unavailable_reports_truthful_state(self) -> None:
        with unittest.mock.patch.object(semantic_uia, "_uia", None):
            adapter = WindowsUIAutomationAdapter(self.provider)  # type: ignore[arg-type]
            self.assertFalse(adapter.available)
            result = await adapter.inspect_window("window-1")
            self.assertEqual(result.status, "failed")
            self.assertEqual(result.error_code, "uia_not_available")
            result = await adapter.list_windows("device-1")
            self.assertEqual(result.error_code, "uia_not_available")
            result = await adapter.get_element("element-anything")
            self.assertEqual(result.error_code, "uia_not_available")

    # -- window reference safety --

    async def test_window_ref_stale_returns_typed_result(self) -> None:
        result = await self.adapter.inspect_window("window-does-not-exist")
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "uia_window_stale")

    async def test_sensitive_window_denied(self) -> None:
        provider = _FakeWindowProvider({"window-1": 111}, deny_refs=frozenset({"window-1"}))
        adapter = _adapter({111: self.root}, provider)
        result = await adapter.inspect_window("window-1")
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error_code, "sensitive_window_denied")

    # -- bounded tree inspection --

    async def test_bounded_tree_depth(self) -> None:
        leaf = _FakeControl("Level4", "TextControl", runtime_id=(9, 4))
        level3 = _FakeControl("Level3", "GroupControl", runtime_id=(9, 3), children=[leaf])
        level2 = _FakeControl("Level2", "GroupControl", runtime_id=(9, 2), children=[level3])
        level1 = _FakeControl("Level1", "GroupControl", runtime_id=(9, 1), children=[level2])
        deep_root = _FakeControl("Level0", "WindowControl", runtime_id=(9, 0), children=[level1])
        provider = _FakeWindowProvider({"window-deep": 222})
        adapter = _adapter({222: deep_root}, provider)

        result = await adapter.inspect_window("window-deep", depth=2)
        self.assertEqual(result.status, "succeeded")
        names: list[str | None] = []

        def collect(node: semantic_uia.SemanticTreeNode) -> None:
            names.append(node.snapshot.name)
            for child in node.children:
                collect(child)

        collect(result.output["tree"])
        self.assertIn("Level0", names)
        self.assertIn("Level1", names)
        self.assertIn("Level2", names)
        self.assertNotIn("Level3", names)
        self.assertNotIn("Level4", names)

    async def test_bounded_node_count(self) -> None:
        many_children = [_FakeControl(f"Item{i}", "ButtonControl", runtime_id=(5, i)) for i in range(400)]
        wide_root = _FakeControl("Wide", "WindowControl", runtime_id=(5,), children=many_children)
        provider = _FakeWindowProvider({"window-wide": 333})
        adapter = _adapter({333: wide_root}, provider)

        result = await adapter.inspect_window("window-wide")
        self.assertEqual(result.status, "succeeded")
        self.assertLessEqual(result.output["element_count"], semantic_uia.MAX_TREE_ELEMENTS)
        self.assertTrue(result.output["truncated"])

    # -- semantic search --

    async def test_find_by_automation_id(self) -> None:
        result = await self.adapter.find_elements("window-1", automation_id="num7Button")
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(len(result.output["matches"]), 1)
        self.assertEqual(result.output["matches"][0].name, "Seven")
        self.assertFalse(result.output["ambiguous"])

    async def test_find_by_name_and_control_type(self) -> None:
        result = await self.adapter.find_elements("window-1", control_type="ButtonControl", name="Eight")
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(len(result.output["matches"]), 1)
        self.assertEqual(result.output["matches"][0].automation_id, "num8Button")

    async def test_ambiguous_match_stays_ambiguous(self) -> None:
        dup_a = _FakeControl("Duplicate", "ButtonControl", runtime_id=(2, 1))
        dup_b = _FakeControl("Duplicate", "ButtonControl", runtime_id=(2, 2))
        root = _FakeControl("Win", "WindowControl", runtime_id=(2,), children=[dup_a, dup_b])
        provider = _FakeWindowProvider({"window-dup": 444})
        adapter = _adapter({444: root}, provider)

        result = await adapter.find_elements("window-dup", name="Duplicate")
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(len(result.output["matches"]), 2)
        self.assertTrue(result.output["ambiguous"])

    async def test_find_requires_at_least_one_filter(self) -> None:
        result = await self.adapter.find_elements("window-1")
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error_code, "uia_find_filter_required")

    # -- element reference lifecycle --

    async def test_element_ref_expires(self) -> None:
        found = await self.adapter.find_elements("window-1", automation_id="num7Button")
        ref = found.output["matches"][0].element_ref
        self.adapter._element_refs[ref].expires_at = datetime.now(UTC) - timedelta(seconds=1)
        result = await self.adapter.get_element(ref)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "uia_element_stale")

    async def test_element_ref_reresolution_success(self) -> None:
        found = await self.adapter.find_elements("window-1", automation_id="num7Button")
        ref = found.output["matches"][0].element_ref
        result = await self.adapter.get_element(ref)
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(result.output["element"].name, "Seven")
        self.assertEqual(result.output["element"].element_ref, ref)

    async def test_stale_element_never_silently_resolves_to_different_element(self) -> None:
        found = await self.adapter.find_elements("window-1", automation_id="num7Button")
        ref = found.output["matches"][0].element_ref

        # Simulate the window being torn down and rebuilt: a *different* element now
        # carries the same AutomationId/Name but a different underlying identity.
        impostor = _FakeControl("Seven", "ButtonControl", automation_id="num7Button", runtime_id=(1, 999))
        new_group = _FakeControl("Numbers", "GroupControl", runtime_id=(1, 0), children=[impostor, self.eight])
        new_root = _FakeControl("Calculator", "WindowControl", runtime_id=(1,), children=[new_group])
        self.adapter._control_from_handle = lambda hwnd: {111: new_root}.get(hwnd)

        result = await self.adapter.get_element(ref)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "uia_element_stale")

        # And the impostor must not be reachable at all through the old ref. The
        # first stale detection above already purged the ref from the store, so a
        # second call now reports "not found" rather than "stale" - either way,
        # it must never succeed and must never return the impostor's data.
        text_result = await self.adapter.get_text_or_value(ref)
        self.assertEqual(text_result.status, "failed")
        self.assertIn(text_result.error_code, {"uia_element_stale", "uia_element_not_found"})

    async def test_revalidate_reference_reports_explicit_states(self) -> None:
        found = await self.adapter.find_elements("window-1", automation_id="num7Button")
        ref = found.output["matches"][0].element_ref
        valid = await self.adapter.revalidate_reference(ref)
        self.assertEqual(valid.output["state"], "valid")

        missing = await self.adapter.revalidate_reference("element-never-issued")
        self.assertEqual(missing.output["state"], "not_found")

    # -- text/value retrieval --

    async def test_get_text_value_bounded(self) -> None:
        huge_text = "x" * (semantic_uia.MAX_TEXT_LENGTH + 500)
        control = _FakeControl(
            "Document", "DocumentControl", runtime_id=(3, 1),
            patterns={PATTERN_IDS["Text"]: _FakeTextPattern(huge_text)},
        )
        root = _FakeControl("Win", "WindowControl", runtime_id=(3,), children=[control])
        provider = _FakeWindowProvider({"window-doc": 555})
        adapter = _adapter({555: root}, provider)
        found = await adapter.find_elements("window-doc", control_type="DocumentControl")
        ref = found.output["matches"][0].element_ref

        result = await adapter.get_text_or_value(ref)
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(len(result.output["text"]), semantic_uia.MAX_TEXT_LENGTH)
        self.assertTrue(result.output["truncated"])

    async def test_get_text_value_uses_value_pattern_fallback(self) -> None:
        control = _FakeControl(
            "Box", "EditControl", runtime_id=(4, 1),
            patterns={PATTERN_IDS["Value"]: _FakeValuePattern("hello")},
        )
        root = _FakeControl("Win", "WindowControl", runtime_id=(4,), children=[control])
        provider = _FakeWindowProvider({"window-edit": 666})
        adapter = _adapter({666: root}, provider)
        found = await adapter.find_elements("window-edit", control_type="EditControl")
        ref = found.output["matches"][0].element_ref

        result = await adapter.get_text_or_value(ref)
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(result.output["text"], "hello")

    async def test_password_sensitive_value_redacted(self) -> None:
        control = _FakeControl(
            "Password", "EditControl", runtime_id=(6, 1), is_password=True,
            patterns={PATTERN_IDS["Value"]: _FakeValuePattern("hunter2")},
        )
        root = _FakeControl("Win", "WindowControl", runtime_id=(6,), children=[control])
        provider = _FakeWindowProvider({"window-pw": 777})
        adapter = _adapter({777: root}, provider)
        found = await adapter.find_elements("window-pw", control_type="EditControl")
        ref = found.output["matches"][0].element_ref

        result = await adapter.get_text_or_value(ref)
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error_code, "uia_sensitive_value_denied")
        self.assertNotIn("hunter2", str(result.output))

    # -- boundary purity --

    async def test_no_raw_hwnd_or_com_object_in_public_snapshot(self) -> None:
        found = await self.adapter.find_elements("window-1", automation_id="num7Button")
        snapshot = found.output["matches"][0]
        self.assertIsInstance(snapshot, SemanticElementSnapshot)
        field_names = {f.name for f in dataclasses.fields(snapshot)}
        self.assertEqual(
            field_names,
            {
                "element_ref", "window_ref", "name", "control_type", "automation_id",
                "enabled", "offscreen", "focused", "focusable", "bounds",
                "supported_patterns", "text", "observed_at",
            },
        )
        for value in dataclasses.astuple(snapshot):
            self.assertNotIsInstance(value, _FakeControl)
        self.assertTrue(snapshot.element_ref.startswith("element-"))
        self.assertIn("Invoke", snapshot.supported_patterns)

    # -- Milestone 3: bounded semantic actions --

    async def test_invoke_calls_pattern_and_is_never_verified_true_generically(self) -> None:
        pattern = _FakeInvokePattern()
        control = _FakeControl("Go", "ButtonControl", runtime_id=(7, 1), patterns={PATTERN_IDS["Invoke"]: pattern})
        root = _FakeControl("Win", "WindowControl", runtime_id=(7,), children=[control])
        provider = _FakeWindowProvider({"window-act": 888})
        adapter = _adapter({888: root}, provider)
        found = await adapter.find_elements("window-act", automation_id=None, control_type="ButtonControl")
        ref = found.output["matches"][0].element_ref

        result = await adapter.invoke(ref)
        self.assertEqual(result.status, "succeeded")
        self.assertTrue(pattern.invoked)
        self.assertFalse(result.output["verified"])

    async def test_invoke_unsupported_pattern_returns_typed_failure(self) -> None:
        control = _FakeControl("Label", "TextControl", runtime_id=(7, 2))
        root = _FakeControl("Win", "WindowControl", runtime_id=(7,), children=[control])
        provider = _FakeWindowProvider({"window-act2": 889})
        adapter = _adapter({889: root}, provider)
        found = await adapter.find_elements("window-act2", control_type="TextControl")
        ref = found.output["matches"][0].element_ref

        result = await adapter.invoke(ref)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "uia_pattern_unsupported")

    async def test_invoke_on_password_control_denied_before_pattern_check(self) -> None:
        pattern = _FakeInvokePattern()
        control = _FakeControl(
            "Secret", "ButtonControl", runtime_id=(7, 3), is_password=True,
            patterns={PATTERN_IDS["Invoke"]: pattern},
        )
        root = _FakeControl("Win", "WindowControl", runtime_id=(7,), children=[control])
        provider = _FakeWindowProvider({"window-act3": 890})
        adapter = _adapter({890: root}, provider)
        found = await adapter.find_elements("window-act3", control_type="ButtonControl")
        ref = found.output["matches"][0].element_ref

        result = await adapter.invoke(ref)
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error_code, "uia_sensitive_value_denied")
        self.assertFalse(pattern.invoked)

    async def test_invoke_on_stale_element_never_acts(self) -> None:
        pattern = _FakeInvokePattern()
        control = _FakeControl("Go", "ButtonControl", runtime_id=(7, 4), patterns={PATTERN_IDS["Invoke"]: pattern})
        root = _FakeControl("Win", "WindowControl", runtime_id=(7,), children=[control])
        provider = _FakeWindowProvider({"window-act4": 891})
        adapter = _adapter({891: root}, provider)
        found = await adapter.find_elements("window-act4", control_type="ButtonControl")
        ref = found.output["matches"][0].element_ref
        adapter._element_refs[ref].expires_at = datetime.now(UTC) - timedelta(seconds=1)

        result = await adapter.invoke(ref)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "uia_element_stale")
        self.assertFalse(pattern.invoked)

    async def test_invoke_on_ambiguous_reresolution_never_acts(self) -> None:
        dup_a = _FakeControl("Dup", "ButtonControl", runtime_id=(8, 1))
        root = _FakeControl("Win", "WindowControl", runtime_id=(8,), children=[dup_a])
        provider = _FakeWindowProvider({"window-amb": 892})
        adapter = _adapter({892: root}, provider)
        found = await adapter.find_elements("window-amb", control_type="ButtonControl")
        ref = found.output["matches"][0].element_ref

        # Make the containing window now expose two elements with the SAME RuntimeId
        # digest (a pathological/duplicate-identity scenario) - re-resolution must
        # refuse to guess which one is the real target.
        dup_b = _FakeControl("Dup", "ButtonControl", runtime_id=(8, 1))
        pattern_a = _FakeInvokePattern()
        dup_a._patterns = {PATTERN_IDS["Invoke"]: pattern_a}
        new_root = _FakeControl("Win", "WindowControl", runtime_id=(8,), children=[dup_a, dup_b])
        adapter._control_from_handle = lambda hwnd: {892: new_root}.get(hwnd)

        result = await adapter.invoke(ref)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "uia_element_ambiguous")
        self.assertFalse(pattern_a.invoked)

    async def test_toggle_verified_true_when_state_actually_changes(self) -> None:
        pattern = _FakeTogglePattern(initial_state=0)
        control = _FakeControl("Check", "CheckBoxControl", runtime_id=(9, 1), patterns={PATTERN_IDS["Toggle"]: pattern})
        root = _FakeControl("Win", "WindowControl", runtime_id=(9,), children=[control])
        provider = _FakeWindowProvider({"window-tog": 893})
        adapter = _adapter({893: root}, provider)
        found = await adapter.find_elements("window-tog", control_type="CheckBoxControl")
        ref = found.output["matches"][0].element_ref

        result = await adapter.toggle(ref)
        self.assertEqual(result.status, "succeeded")
        self.assertTrue(result.output["verified"])
        self.assertEqual(result.output["toggle_state_before"], 0)
        self.assertEqual(result.output["toggle_state_after"], 1)

    async def test_toggle_verified_false_when_state_does_not_change(self) -> None:
        pattern = _FakeTogglePattern(initial_state=0, stuck=True)
        control = _FakeControl("Check", "CheckBoxControl", runtime_id=(9, 2), patterns={PATTERN_IDS["Toggle"]: pattern})
        root = _FakeControl("Win", "WindowControl", runtime_id=(9,), children=[control])
        provider = _FakeWindowProvider({"window-tog2": 894})
        adapter = _adapter({894: root}, provider)
        found = await adapter.find_elements("window-tog2", control_type="CheckBoxControl")
        ref = found.output["matches"][0].element_ref

        result = await adapter.toggle(ref)
        self.assertEqual(result.status, "succeeded")
        self.assertFalse(result.output["verified"])

    async def test_select_verified_true_when_selected(self) -> None:
        pattern = _FakeSelectionItemPattern()
        control = _FakeControl("Item", "ListItemControl", runtime_id=(10, 1), patterns={PATTERN_IDS["SelectionItem"]: pattern})
        root = _FakeControl("Win", "WindowControl", runtime_id=(10,), children=[control])
        provider = _FakeWindowProvider({"window-sel": 895})
        adapter = _adapter({895: root}, provider)
        found = await adapter.find_elements("window-sel", control_type="ListItemControl")
        ref = found.output["matches"][0].element_ref

        result = await adapter.select(ref)
        self.assertEqual(result.status, "succeeded")
        self.assertTrue(result.output["verified"])

    async def test_select_verified_false_when_not_selected(self) -> None:
        pattern = _FakeSelectionItemPattern(stuck=True)
        control = _FakeControl("Item", "ListItemControl", runtime_id=(10, 2), patterns={PATTERN_IDS["SelectionItem"]: pattern})
        root = _FakeControl("Win", "WindowControl", runtime_id=(10,), children=[control])
        provider = _FakeWindowProvider({"window-sel2": 896})
        adapter = _adapter({896: root}, provider)
        found = await adapter.find_elements("window-sel2", control_type="ListItemControl")
        ref = found.output["matches"][0].element_ref

        result = await adapter.select(ref)
        self.assertEqual(result.status, "succeeded")
        self.assertFalse(result.output["verified"])


if __name__ == "__main__":
    unittest.main()
