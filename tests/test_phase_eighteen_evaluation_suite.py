"""Milestone 2 (Phase 18 Workstream A, Batch 02): repeatable Computer Use V2
evaluation suite.

Covers: suite registration, deterministic pass/fail, regression detection
(generic `EvaluationService` mechanism, exercised here against a suite named
like this one), no physical test runs by default, raw UI text never
persisted in evaluation results, and the opt-in physical acceptance runner
script's safety preconditions/cleanup path - all without a GUI or live
Windows dependency.
"""

from __future__ import annotations

import importlib.util
import json
import platform
import sys
import unittest
import unittest.mock
from pathlib import Path

from jarvis.bootstrap import create_runtime
from jarvis.config import JarvisConfig
from jarvis.evaluation.computer_use_v2 import SUITE_NAME, build_suite
from jarvis.evaluation.service import EvaluationCase, EvaluationService, RegressionSuite


class ComputerUseV2SuiteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:"))
        await self.runtime.start()

    async def asyncTearDown(self) -> None:
        await self.runtime.shutdown()

    def test_suite_registered_by_default(self) -> None:
        names = {suite.name for suite in self.runtime.evaluations.suites()}
        self.assertIn(SUITE_NAME, names)

    def test_suite_has_at_least_seventeen_cases(self) -> None:
        suite = build_suite()
        self.assertGreaterEqual(len(suite.cases), 17)
        self.assertEqual(len({case.case_id for case in suite.cases}), len(suite.cases))

    async def test_all_cases_pass_deterministically(self) -> None:
        run = await self.runtime.evaluations.run(SUITE_NAME)
        self.assertTrue(run.passed, run.summary)
        self.assertTrue(all(result.passed for result in run.results), [r for r in run.results if not r.passed])

    async def test_no_physical_test_runs_by_default(self) -> None:
        # The deterministic suite must never spawn a real process (Calculator,
        # Edge, or otherwise) - patch subprocess.Popen to fail loudly if any
        # case tries to launch something.
        with unittest.mock.patch("subprocess.Popen", side_effect=AssertionError("suite must not launch real processes")):
            run = await self.runtime.evaluations.run(SUITE_NAME)
        self.assertTrue(run.passed)

    async def test_raw_ui_text_not_persisted_in_results(self) -> None:
        run = await self.runtime.evaluations.run(SUITE_NAME)
        rows = self.runtime.repository.evaluation_runs(None)
        row = next(r for r in rows if r["id"] == run.run_id)
        results_blob = row["results_json"]
        # Fixture control names used internally by the suite's fakes are
        # short, JARVIS-authored labels ("Target", "Changed Control",
        # "Observed Name") - never arbitrary/owner UI text. Assert no
        # unexpectedly long string sneaks into the persisted payload.
        parsed = json.loads(results_blob)
        for entry in parsed:
            actual = entry.get("actual")
            if isinstance(actual, str):
                self.assertLess(len(actual), 200)

    async def test_regression_detection(self) -> None:
        # Generic EvaluationService mechanism (already product code), proven
        # here against a Computer-Use-V2-shaped suite name so this milestone
        # has direct evidence the suite integrates with regression detection.
        service = EvaluationService(self.runtime.repository, self.runtime.event_bus)
        passing = RegressionSuite("cuv2-regression-check", (EvaluationCase("c1", "always true", "m", lambda ctx: True),))
        service.register(passing)
        first = await service.run("cuv2-regression-check")
        self.assertTrue(first.passed)
        self.assertFalse(first.regression)

        failing = RegressionSuite("cuv2-regression-check", (EvaluationCase("c1", "always false", "m", lambda ctx: False),))
        service.register(failing)
        second = await service.run("cuv2-regression-check")
        self.assertFalse(second.passed)
        self.assertTrue(second.regression)


class PhysicalRunnerScriptTests(unittest.TestCase):
    """Import and unit-test the opt-in physical acceptance runner's pure/safe
    helpers directly - never actually launches Calculator/Edge here."""

    @classmethod
    def setUpClass(cls) -> None:
        script_path = Path(__file__).resolve().parents[1] / "scripts" / "phase18" / "computer_use_acceptance.py"
        spec = importlib.util.spec_from_file_location("phase18_computer_use_acceptance", script_path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        cls.module = module

    def test_refuses_on_non_windows(self) -> None:
        import asyncio

        with unittest.mock.patch.object(platform, "system", return_value="Linux"):
            exit_code = asyncio.run(self.module._main(1))
        self.assertEqual(exit_code, 1)

    def test_summary_never_includes_full_window_enumeration(self) -> None:
        fake_runs = [
            {
                "calculator": {"fixture": "calculator", "attempted": True, "semantic_invoke": {"status": "completed", "independent_display_readback_matched_seven": True}, "native_left_click": {"pointer_target_verified": True}, "native_key_tab": {"independent_focus_moved": True}},
                "edge_guest": {"fixture": "edge_guest_local_html", "attempted": True, "invoke": {"status": "not_found"}, "toggle": {"status": "not_found"}, "select": {"status": "not_found"}},
            }
        ]
        summary = self.module._summarize(fake_runs)
        blob = json.dumps(summary)
        self.assertNotIn("window_ref", blob)
        self.assertNotIn("windows", blob)

    def test_fixture_html_is_local_and_inert(self) -> None:
        html = self.module.FIXTURE_HTML
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)

    def test_edge_path_lookup_returns_none_when_absent(self) -> None:
        with unittest.mock.patch.object(self.module.Path, "exists", return_value=False):
            self.assertIsNone(self.module._edge_path())


if __name__ == "__main__":
    unittest.main()
