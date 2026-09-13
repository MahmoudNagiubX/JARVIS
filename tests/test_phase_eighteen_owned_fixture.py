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
import tempfile
import unittest
import unittest.mock
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER_SCRIPT = REPO_ROOT / "scripts" / "phase18" / "computer_use_acceptance.py"
FIXTURE_SCRIPT = REPO_ROOT / "scripts" / "phase18" / "uia_fixture_host.py"
TEXT_FIXTURE_SCRIPT = REPO_ROOT / "scripts" / "phase18" / "uia_text_fixture_host.py"
OCR_BENCHMARK_SCRIPT = REPO_ROOT / "scripts" / "phase18" / "ocr_backend_benchmark.py"
OCR_FIXTURE_SCRIPT = REPO_ROOT / "scripts" / "phase18" / "uia_ocr_fixture_host.py"
OCR_ACCEPTANCE_RUNNER_SCRIPT = REPO_ROOT / "scripts" / "phase18" / "ocr_visual_acceptance.py"
PROVISION_SCRIPT = REPO_ROOT / "scripts" / "setup" / "provision_easyocr_models.py"
RECOVERY_FIXTURE_SCRIPT = REPO_ROOT / "scripts" / "phase18" / "uia_recovery_fixture_host.py"


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


class OcrBenchmarkSourceSafetyTests(unittest.TestCase):
    """Batch 04 Milestone 2: the OCR backend benchmark is an evaluation-only
    dev tool (never a production dependency) - no owner data, no persisted
    model weights/images, never imported by production bootstrap."""

    def test_benchmark_not_imported_by_production_bootstrap(self) -> None:
        bootstrap_source = (REPO_ROOT / "src" / "jarvis" / "bootstrap.py").read_text(encoding="utf-8")
        self.assertNotIn("ocr_backend_benchmark", bootstrap_source)

    def test_benchmark_not_imported_anywhere_under_src(self) -> None:
        for path in (REPO_ROOT / "src").rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("ocr_backend_benchmark", source, f"unexpected reference in {path}")

    def test_benchmark_deletes_generated_images_after_running(self) -> None:
        source = OCR_BENCHMARK_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("unlink", source)

    def test_benchmark_is_syntactically_standalone_script(self) -> None:
        tree = ast.parse(OCR_BENCHMARK_SCRIPT.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level and node.level > 0:
                self.fail("ocr_backend_benchmark.py uses a relative import, unexpected for a standalone dev script")

    def test_benchmark_uses_only_jarvis_owned_synthetic_fixture_text(self) -> None:
        source = OCR_BENCHMARK_SCRIPT.read_text(encoding="utf-8")
        for expected in ("JARVIS COMPUTER USE", "مرحبا يا جارفيس", "الإعدادات"):
            self.assertIn(expected, source)

    def test_benchmark_records_rendering_diagnostics_and_never_silently_scores_unshaped_arabic(self) -> None:
        # R18B04-002: the benchmark must record Pillow version, font path,
        # raqm availability, and the layout engine actually used per
        # fixture, and must fail closed (FIXTURE_RENDERING_INVALID) rather
        # than silently generate an accuracy score for Arabic/mixed text
        # when no proven complex-text shaping path is available.
        source = OCR_BENCHMARK_SCRIPT.read_text(encoding="utf-8")
        for expected in (
            "FIXTURE_RENDERING_INVALID", "raqm_feature_available", "pillow_version",
            "font_path", "per_fixture_layout_engine", "arabic_reshaper", "python-bidi",
            "scoring_method",
        ):
            self.assertIn(expected, source)


class OcrBenchmarkRenderingTests(unittest.TestCase):
    """Functional coverage of the R18B04-002 fixture-rendering contract -
    exercises the real `render_fixture_images()` function (pure, no OCR
    package dependency), never a real OCR backend."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.module = _load_module(OCR_BENCHMARK_SCRIPT, "phase18_ocr_benchmark_test_target")

    def test_english_fixtures_always_render_without_shaping(self) -> None:
        with tempfile.TemporaryDirectory(prefix="jarvis_ocr_render_") as tmp:
            fixtures, _diagnostics = self.module.render_fixture_images(Path(tmp))
            english = [f for f in fixtures if f.category == "english"]
            self.assertEqual(len(english), 3)
            for fixture in english:
                self.assertTrue(fixture.rendering_valid)
                assert fixture.path is not None
                self.assertTrue(fixture.path.exists())

    def test_arabic_and_mixed_fixtures_fail_closed_without_a_proven_shaping_path(self) -> None:
        # On this machine, neither PIL raqm nor arabic_reshaper+python-bidi
        # is installed in the environment running the test suite - proving
        # the fail-closed contract rather than a silently-garbled score.
        with tempfile.TemporaryDirectory(prefix="jarvis_ocr_render_") as tmp:
            fixtures, diagnostics = self.module.render_fixture_images(Path(tmp))
            if diagnostics.raqm_feature_available or (
                diagnostics.arabic_reshaper_available and diagnostics.python_bidi_available
            ):
                self.skipTest("a valid Arabic shaping path is available in this environment")
            arabic_and_mixed = [f for f in fixtures if f.category in ("arabic", "mixed")]
            self.assertEqual(len(arabic_and_mixed), 4)
            for fixture in arabic_and_mixed:
                self.assertFalse(fixture.rendering_valid)
                self.assertIsNone(fixture.path)
                self.assertIsNone(fixture.layout_engine)
                assert fixture.rendering_error is not None
                self.assertIn("FIXTURE_RENDERING_INVALID", fixture.rendering_error)

    def test_expected_scoring_text_is_never_the_reshaped_presentation_form(self) -> None:
        # The ground truth used for scoring must always be the original
        # semantic Unicode string, never Arabic-presentation-form glyphs
        # used only for rendering.
        with tempfile.TemporaryDirectory(prefix="jarvis_ocr_render_") as tmp:
            fixtures, _diagnostics = self.module.render_fixture_images(Path(tmp))
        original_texts = {text for entries in self.module.FIXTURES.values() for text in entries}
        for fixture in fixtures:
            self.assertIn(fixture.expected_text, original_texts)
            # Arabic presentation-form codepoints (U+FB50-FDFF, U+FE70-FEFF)
            # must never appear in the text used for scoring.
            self.assertFalse(any("ﭐ" <= ch <= "﷿" or "ﹰ" <= ch <= "﻿" for ch in fixture.expected_text))


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
            "recovery_fixture": {
                "attempted": True,
                "relocation_before_input": {"click_landed_on_same_generation": True, "bounds_changed": True},
                "approval_identity_change": {"refused_before_any_input": True, "zero_input_delivered": True},
                "fixture_child_confirmed_exited": True,
            },
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


class OcrFixtureSourceSafetyTests(unittest.TestCase):
    """Batch 06 Milestone 1: the third owned fixture (OCR/visual
    acceptance) and its dedicated physical runner carry the same safety
    discipline as the first two fixtures - JARVIS-owned child process only,
    no owner app/file/network/clipboard, exact-PID cleanup, never imported
    by production, and real Arabic Unicode (never a Latin transliteration)."""

    def test_fixture_host_has_no_owner_application_dependency(self) -> None:
        source = OCR_FIXTURE_SCRIPT.read_text(encoding="utf-8").casefold()
        for forbidden in ("msedge", "notepad.exe", "calc.exe", "chrome.exe"):
            self.assertNotIn(forbidden, source)

    def test_fixture_host_has_no_network_clipboard_or_file_dialog_calls(self) -> None:
        # The docstring itself says "no network, no clipboard" (prose
        # explaining what this fixture deliberately does NOT do) - only the
        # executable source below it is checked.
        tree = ast.parse(OCR_FIXTURE_SCRIPT.read_text(encoding="utf-8"))
        module_docstring = ast.get_docstring(tree) or ""
        source = OCR_FIXTURE_SCRIPT.read_text(encoding="utf-8")
        source_without_docstring = source.replace(module_docstring, "").casefold()
        for forbidden in ("socket", "urllib", "http", "getopenfilename", "getsavefilename", "clipboard", "openclipboard"):
            self.assertNotIn(forbidden, source_without_docstring)

    def test_fixture_uses_real_arabic_unicode_not_a_latin_transliteration(self) -> None:
        module = _load_module(OCR_FIXTURE_SCRIPT, "jarvis_test_ocr_fixture_host")
        self.assertEqual(module.LABEL_ARABIC_GREETING, "مرحبا يا جارفيس")
        self.assertEqual(module.LABEL_ARABIC_SETTINGS, "الإعدادات")
        self.assertEqual(module.LABEL_MIXED_SETTINGS, "JARVIS الإعدادات")
        # Every character in the Arabic-only labels must actually fall in
        # the Arabic Unicode block - guards against an accidental future
        # substitution with a Latin transliteration ("marhaban ya jarvis").
        for char in module.LABEL_ARABIC_GREETING.replace(" ", ""):
            self.assertTrue("؀" <= char <= "ۿ", f"unexpected non-Arabic character {char!r}")
        for char in module.LABEL_ARABIC_SETTINGS.replace(" ", ""):
            self.assertTrue("؀" <= char <= "ۿ", f"unexpected non-Arabic character {char!r}")

    def test_fixture_not_imported_by_production_bootstrap(self) -> None:
        bootstrap_source = (REPO_ROOT / "src" / "jarvis" / "bootstrap.py").read_text(encoding="utf-8")
        self.assertNotIn("uia_ocr_fixture_host", bootstrap_source)
        self.assertNotIn("ocr_visual_acceptance", bootstrap_source)

    def test_fixture_and_runner_not_imported_anywhere_under_src(self) -> None:
        for path in (REPO_ROOT / "src").rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("uia_ocr_fixture_host", source, f"unexpected reference in {path}")
            self.assertNotIn("ocr_visual_acceptance", source, f"unexpected reference in {path}")

    def test_provisioning_script_never_actually_imported_under_src(self) -> None:
        # `provision_easyocr_models` IS legitimately mentioned in prose
        # inside `visual_ocr.py`'s own docstring/comments (pointing a
        # developer at the setup step) - the property that actually matters
        # is that no `import` statement anywhere under src/ ever references
        # it, not that the name is never written down.
        for path in (REPO_ROOT / "src").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotIn("provision_easyocr_models", alias.name, f"unexpected import in {path}")
                elif isinstance(node, ast.ImportFrom) and node.module:
                    self.assertNotIn("provision_easyocr_models", node.module, f"unexpected import in {path}")

    def test_scripts_are_syntactically_standalone(self) -> None:
        for script in (OCR_FIXTURE_SCRIPT, OCR_ACCEPTANCE_RUNNER_SCRIPT, PROVISION_SCRIPT):
            tree = ast.parse(script.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.level and node.level > 0:
                    self.fail(f"{script.name} uses a relative import, unexpected for a standalone dev script")

    def test_runner_cleanup_uses_exact_pid_not_broad_taskkill(self) -> None:
        tree = ast.parse(OCR_ACCEPTANCE_RUNNER_SCRIPT.read_text(encoding="utf-8"))
        module_docstring = ast.get_docstring(tree) or ""
        source_without_docstring = OCR_ACCEPTANCE_RUNNER_SCRIPT.read_text(encoding="utf-8").replace(module_docstring, "")
        self.assertNotIn("taskkill", source_without_docstring.casefold())
        self.assertIn("proc.terminate()", source_without_docstring)
        self.assertIn("proc.wait(", source_without_docstring)

    def test_runner_never_reads_owner_clipboard(self) -> None:
        source = OCR_ACCEPTANCE_RUNNER_SCRIPT.read_text(encoding="utf-8").casefold()
        self.assertNotIn("clipboard", source)

    def test_runner_has_no_owner_application_dependency(self) -> None:
        source = OCR_ACCEPTANCE_RUNNER_SCRIPT.read_text(encoding="utf-8").casefold()
        for forbidden in ("msedge", "notepad.exe", "calc.exe", "chrome.exe", "explorer.exe"):
            self.assertNotIn(forbidden, source)


class RecoveryFixtureSourceSafetyTests(unittest.TestCase):
    """Batch 06 Milestone 2 (GAP-0104): the fourth owned fixture (bounded
    pre-input recovery acceptance) accepts a small deterministic MOVE/
    REPLACE command channel over its own stdin - the same safety discipline
    as the other three fixtures otherwise applies unchanged: JARVIS-owned
    child process only, no owner app/network/clipboard, exact-PID cleanup,
    never imported by production."""

    def test_fixture_host_has_no_owner_application_dependency(self) -> None:
        source = RECOVERY_FIXTURE_SCRIPT.read_text(encoding="utf-8").casefold()
        for forbidden in ("msedge", "notepad.exe", "calc.exe", "chrome.exe"):
            self.assertNotIn(forbidden, source)

    def test_fixture_host_has_no_network_or_clipboard_calls(self) -> None:
        tree = ast.parse(RECOVERY_FIXTURE_SCRIPT.read_text(encoding="utf-8"))
        module_docstring = ast.get_docstring(tree) or ""
        source_without_docstring = RECOVERY_FIXTURE_SCRIPT.read_text(encoding="utf-8").replace(module_docstring, "").casefold()
        for forbidden in ("socket", "urllib", "http", "getopenfilename", "getsavefilename", "clipboard", "openclipboard"):
            self.assertNotIn(forbidden, source_without_docstring)

    def test_fixture_command_channel_is_scoped_to_its_own_stdin_only(self) -> None:
        # The only inter-process channel this fixture accepts is the stdin
        # pipe of the exact child process a runner itself created via
        # subprocess.Popen(..., stdin=subprocess.PIPE) - never a network
        # socket, named pipe, or shared file reaching an unrelated process.
        source = RECOVERY_FIXTURE_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("sys.stdin", source)
        self.assertNotIn("CreateNamedPipe", source)
        self.assertNotIn("CreateFile", source)

    def test_fixture_commands_are_bounded_to_the_documented_set(self) -> None:
        module = _load_module(RECOVERY_FIXTURE_SCRIPT, "jarvis_test_recovery_fixture_host")
        # Only MOVE/REPLACE are recognized - any other stdin line is a no-op
        # (silently ignored, matching the fixture's own `elif` chain).
        source = RECOVERY_FIXTURE_SCRIPT.read_text(encoding="utf-8")
        self.assertIn('command == "MOVE"', source)
        self.assertIn('command == "REPLACE"', source)
        self.assertEqual(module.TARGET_LABEL, "Recovery Target")

    def test_fixture_not_imported_by_production_bootstrap(self) -> None:
        bootstrap_source = (REPO_ROOT / "src" / "jarvis" / "bootstrap.py").read_text(encoding="utf-8")
        self.assertNotIn("uia_recovery_fixture_host", bootstrap_source)

    def test_fixture_not_imported_anywhere_under_src(self) -> None:
        for path in (REPO_ROOT / "src").rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("uia_recovery_fixture_host", source, f"unexpected reference in {path}")

    def test_fixture_is_syntactically_standalone(self) -> None:
        tree = ast.parse(RECOVERY_FIXTURE_SCRIPT.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level and node.level > 0:
                self.fail(f"{RECOVERY_FIXTURE_SCRIPT.name} uses a relative import, unexpected for a standalone dev script")

    def test_runner_recovery_scenario_uses_exact_pid_cleanup(self) -> None:
        source = RUNNER_SCRIPT.read_text(encoding="utf-8")
        # The recovery scenario function itself, not just the runner file in
        # general, must close its own stdin pipe and confirm exact-PID exit.
        start = source.index("async def _run_recovery_fixture_scenarios")
        end = source.index("\n\n\n", start)
        scenario_source = source[start:end]
        self.assertIn("proc.terminate()", scenario_source)
        self.assertIn("proc.wait(", scenario_source)
        self.assertIn("fixture_child_confirmed_exited", scenario_source)


if __name__ == "__main__":
    unittest.main()
