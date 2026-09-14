"""Batch 07 Milestone 2 regression coverage for owned multi-window breadth."""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
import unittest.mock
from pathlib import Path

from jarvis.bootstrap import create_runtime
from jarvis.config import JarvisConfig
from jarvis.evaluation.computer_use_v2 import build_suite
from jarvis.perception.windows import WindowsDesktopProvider


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER_SCRIPT = REPO_ROOT / "scripts" / "phase18" / "computer_use_acceptance.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("phase18_multi_window_runner_test_target", RUNNER_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class MultiWindowEvaluationTests(unittest.IsolatedAsyncioTestCase):
    async def test_suite_adds_only_the_two_new_child_window_contract_cases(self) -> None:
        suite = build_suite()
        ids = [case.case_id for case in suite.cases]
        self.assertEqual(ids[-2:], ["cuv2-47", "cuv2-48"])
        self.assertEqual(len(ids), 48)
        runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:"))
        await runtime.start()
        try:
            run = await runtime.evaluations.run(suite)
            self.assertTrue(run.passed, run.summary)
        finally:
            await runtime.shutdown()


class MultiWindowRunnerSummaryTests(unittest.TestCase):
    def test_provider_ownership_predicate_compares_the_fresh_live_pid(self) -> None:
        provider = object.__new__(WindowsDesktopProvider)
        provider.validate_input_window = lambda window_ref: 77  # type: ignore[method-assign]
        provider._user32 = unittest.mock.Mock()

        def _write_pid(_hwnd, target) -> None:
            target._obj.value = 901

        provider._user32.GetWindowThreadProcessId.side_effect = _write_pid
        self.assertTrue(provider.window_belongs_to_process("window-owned", 901))
        self.assertFalse(provider.window_belongs_to_process("window-owned", 902))
        self.assertFalse(provider.window_belongs_to_process("window-owned", True))

    def test_runner_uses_canonical_provider_for_exact_process_ownership(self) -> None:
        source = RUNNER_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("window_belongs_to_process", source)
        self.assertNotIn('match.get("process_id")', source)

    def test_summary_records_five_bounded_scenarios_without_window_inventory(self) -> None:
        runner = _load_runner()
        summary = runner._summarize([{
            "owned_fixture": {},
            "text_drag_fixture": {},
            "recovery_fixture": {},
            "non_primary_monitor": {"attempted": False},
            "multi_window_fixture": {
                "attempted": True,
                "owned_dialog_discovery": {"exact_owned_dialog_found": True},
                "dialog_action": {"independent_post_state_matches_expected": True},
                "stale_dialog_target": {"old_target_refused": True},
                "approval_window_transition": {"old_target_refused_before_input": True},
                "focus_window_transition": {"dialog_focus_observed": True, "main_focus_observed": True},
                "close_return": {"dialog_absent_after_close": True, "returned_to_primary": True},
                "fixture_child_confirmed_exited": True,
            },
        }])
        self.assertEqual(summary["multi_window_owned_dialog_discovery"], "1/1")
        self.assertEqual(summary["multi_window_dialog_action"], "1/1")
        self.assertEqual(summary["multi_window_stale_dialog_target_refused"], "1/1")
        self.assertEqual(summary["multi_window_approval_transition_refused"], "1/1")
        self.assertEqual(summary["multi_window_focus_transition"], "1/1")
        self.assertEqual(summary["multi_window_close_return"], "1/1")
        self.assertEqual(summary["multi_window_fixture_child_confirmed_exited"], "1/1")
        blob = json.dumps(summary)
        self.assertNotIn("window_ref", blob)
        self.assertNotIn("windows", blob)


if __name__ == "__main__":
    unittest.main()
