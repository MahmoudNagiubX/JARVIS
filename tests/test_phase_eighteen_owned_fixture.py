"""Milestone 0 (Phase 18 Workstream A, Batch 03): JARVIS-owned native Win32
UIA fixture host and the rewritten physical acceptance runner.

Covers the safety properties introduced directly in response to the Batch 02
Notepad incident (R18B02-004/005): exact nonce-title matching (never "first
window with a similar title"), collision refusal, exact-PID-only cleanup (no
broad image-name `taskkill`), no dependency on any owner-installed
application, and confirmation the fixture is never imported by production
JARVIS startup.
"""

from __future__ import annotations

import ast
import asyncio
import importlib.util
import sys
import unittest
import unittest.mock
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER_SCRIPT = REPO_ROOT / "scripts" / "phase18" / "computer_use_acceptance.py"
FIXTURE_SCRIPT = REPO_ROOT / "scripts" / "phase18" / "uia_fixture_host.py"
TEXT_FIXTURE_SCRIPT = REPO_ROOT / "scripts" / "phase18" / "uia_text_fixture_host.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class OwnedFixtureSourceSafetyTests(unittest.TestCase):
    """Static source checks - no process is launched for these."""

    def test_runner_contains_no_broad_taskkill(self) -> None:
        # Only the module docstring is allowed to mention "taskkill" in
        # prose (explaining what this runner deliberately does NOT do) -
        # no actual subprocess invocation of it may exist anywhere.
        tree = ast.parse(RUNNER_SCRIPT.read_text(encoding="utf-8"))
        module_docstring = ast.get_docstring(tree) or ""
        source_without_docstring = RUNNER_SCRIPT.read_text(encoding="utf-8").replace(module_docstring, "")
        self.assertNotIn("taskkill", source_without_docstring.casefold())

    def test_runner_has_no_owner_application_dependency(self) -> None:
        source = RUNNER_SCRIPT.read_text(encoding="utf-8").casefold()
        for forbidden in ("msedge", "notepad.exe", "calc.exe", "calculatorapp", "chrome.exe", "explorer.exe"):
            self.assertNotIn(forbidden, source)

    def test_fixture_host_contains_no_owner_application_dependency(self) -> None:
        for script in (FIXTURE_SCRIPT, TEXT_FIXTURE_SCRIPT):
            source = script.read_text(encoding="utf-8").casefold()
            for forbidden in ("msedge", "notepad.exe", "calc.exe", "chrome.exe"):
                self.assertNotIn(forbidden, source)

    def test_fixture_host_has_no_network_or_file_dialog_calls(self) -> None:
        for script in (FIXTURE_SCRIPT, TEXT_FIXTURE_SCRIPT):
            source = script.read_text(encoding="utf-8").casefold()
            for forbidden in ("socket", "urllib", "http", "getopenfilename", "getsavefilename"):
                self.assertNotIn(forbidden, source)

    def test_fixture_not_imported_by_production_bootstrap(self) -> None:
        bootstrap_source = (REPO_ROOT / "src" / "jarvis" / "bootstrap.py").read_text(encoding="utf-8")
        self.assertNotIn("uia_fixture_host", bootstrap_source)
        self.assertNotIn("uia_text_fixture_host", bootstrap_source)
        self.assertNotIn("computer_use_acceptance", bootstrap_source)

    def test_fixture_not_imported_anywhere_under_src(self) -> None:
        for path in (REPO_ROOT / "src").rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("uia_fixture_host", source, f"unexpected reference in {path}")
            self.assertNotIn("uia_text_fixture_host", source, f"unexpected reference in {path}")
            self.assertNotIn("scripts.phase18", source, f"unexpected reference in {path}")

    def test_runner_and_fixture_are_syntactically_standalone_scripts(self) -> None:
        # Confirms these parse as plain scripts (no package-relative imports
        # that would only work if pulled into the production package).
        for script in (RUNNER_SCRIPT, FIXTURE_SCRIPT, TEXT_FIXTURE_SCRIPT):
            tree = ast.parse(script.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.level and node.level > 0:
                    self.fail(f"{script.name} uses a relative import, unexpected for a standalone dev script")


class OwnedFixtureRunnerLogicTests(unittest.IsolatedAsyncioTestCase):
    """Exercises the runner's window-matching/collision logic against a fake
    tool_service - no real fixture process is launched."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.module = _load_module(RUNNER_SCRIPT, "phase18_computer_use_acceptance_test_target")

    def _context(self) -> object:
        return object()

    async def test_rejects_title_collision(self) -> None:
        class _FakeToolService:
            async def execute(self, tool_name, arguments, context):
                from jarvis.tools.service import ToolExecutionStatus
                return _Result(ToolExecutionStatus.COMPLETED, {
                    "windows": [
                        {"window_ref": "window-a", "title": "JARVIS-CUV2-FIXTURE-nonce-1"},
                        {"window_ref": "window-b", "title": "JARVIS-CUV2-FIXTURE-nonce-1"},
                    ]
                })

        class _Result:
            def __init__(self, status, output):
                self.status = status
                self.output = output

        class _FakeRuntime:
            tool_service = _FakeToolService()

        with unittest.mock.patch.object(asyncio, "sleep", unittest.mock.AsyncMock(return_value=None)):
            window_ref, error = await self.module._find_exact_fixture_window(
                _FakeRuntime(), self._context(), "JARVIS-CUV2-FIXTURE-nonce-1"
            )
        self.assertIsNone(window_ref)
        self.assertEqual(error, "fixture_title_collision")

    async def test_never_falls_back_to_similar_title(self) -> None:
        from jarvis.tools.service import ToolExecutionStatus

        class _Result:
            def __init__(self, status, output):
                self.status = status
                self.output = output

        class _FakeToolService:
            async def execute(self, tool_name, arguments, context):
                return _Result(ToolExecutionStatus.COMPLETED, {
                    "windows": [{"window_ref": "window-a", "title": "JARVIS-CUV2-FIXTURE-different-nonce"}]
                })

        class _FakeRuntime:
            tool_service = _FakeToolService()

        with unittest.mock.patch.object(asyncio, "sleep", unittest.mock.AsyncMock(return_value=None)):
            window_ref, error = await self.module._find_exact_fixture_window(
                _FakeRuntime(), self._context(), "JARVIS-CUV2-FIXTURE-my-exact-nonce"
            )
        self.assertIsNone(window_ref)
        self.assertEqual(error, "fixture_window_not_found")

    def test_summary_never_includes_full_window_enumeration_or_owner_titles(self) -> None:
        fake_runs = [{
            "owned_fixture": {
                "attempted": True,
                "invoke": {"independent_status_matches_expected": True},
                "toggle": {"independent_status_matches_expected": True},
                "select": {"independent_status_matches_expected": True},
                "fixture_child_confirmed_exited": True,
            },
            "text_drag_fixture": {
                "attempted": True,
                "drag": {"independent_status_matches_expected": True},
                "literal_typing_english": {"independent_text_readback_matches_expected": True},
                "literal_typing_arabic": {"independent_text_readback_matches_expected": True},
                "native_key_home_end": {"home_marker_prepended": True, "end_marker_appended": True},
                "native_key_backspace": {"one_character_shorter": True},
                "native_key_tab": {"independent_focus_moved": True},
                "native_chord_ctrl_c": {"clipboard_now_holds_fixture_text": True},
                "native_chord_ctrl_z": {"independent_text_changed_from_pre_undo_state": True},
                "fixture_child_confirmed_exited": True,
            },
            "non_primary_monitor": {"attempted": False, "skip_reason": "MULTI_MONITOR_PHYSICAL_PENDING"},
        }]
        summary = self.module._summarize(fake_runs)
        import json
        blob = json.dumps(summary)
        self.assertNotIn("window_ref", blob)
        self.assertNotIn("windows", blob)

    def test_cleanup_uses_exact_pid_terminate_not_broad_kill(self) -> None:
        source = RUNNER_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("proc.terminate()", source)
        self.assertIn("proc.wait(", source)


if __name__ == "__main__":
    unittest.main()
