"""Batch 09 T1 boundary and privacy tests.

These tests exercise only the opt-in dispatcher and injected session seam. They
never start a runtime, open an application, authenticate a service, or send a
message.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from jarvis.computer.service import WindowsNativeComputerController


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / "scripts" / "phase18" / "real_world_computer_use_acceptance.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("phase18_real_world_boundary_test_target", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class RunnerSourceSafetyTests(unittest.TestCase):
    def test_runner_has_no_direct_desktop_or_network_actuation_imports(self) -> None:
        source = RUNNER.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = {
            alias.name.casefold()
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        self.assertNotIn("subprocess", imported)
        self.assertNotIn("socket", imported)
        self.assertNotIn("uiautomation", source.casefold())
        self.assertNotIn("pyautogui", source.casefold())
        self.assertNotIn("sendinput", source.casefold())

    def test_runner_is_not_in_production_startup(self) -> None:
        bootstrap = (REPO_ROOT / "src" / "jarvis" / "bootstrap.py").read_text(encoding="utf-8")
        self.assertNotIn("real_world_computer_use_acceptance", bootstrap)
        for path in (REPO_ROOT / "src").rglob("*.py"):
            self.assertNotIn("real_world_computer_use_acceptance", path.read_text(encoding="utf-8"))

    def test_runner_has_no_unbounded_or_automatic_main_execution(self) -> None:
        tree = ast.parse(RUNNER.read_text(encoding="utf-8"))
        asyncio_runs = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "asyncio"
            and node.func.attr == "run"
        ]
        self.assertEqual(len(asyncio_runs), 1)
        self.assertTrue(any(isinstance(node, ast.If) for node in tree.body))


class RunnerBehaviorTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = _load_runner()

    def _env(self) -> dict[str, str]:
        return {
            self.module.ENABLE_ENV: "1",
            "JARVIS_E2E_OWNER_ID": "owner-test",
            "JARVIS_E2E_DEVICE_ID": "device-test",
        }

    async def test_opt_in_is_required_and_factory_is_not_called(self) -> None:
        called = False

        async def factory(_config):
            nonlocal called
            called = True
            raise AssertionError("owner session factory must not run without opt-in")

        receipt = await self.module.RealWorldAcceptanceRunner(
            env={}, session_factory=factory,
        ).run("RW-CALC-001")
        self.assertEqual(receipt["status"], "OWNER_SESSION_E2E_DISABLED")
        self.assertFalse(called)
        self.assertEqual(receipt["side_effects"], {"external_writes": 0, "sends": 0})

    async def test_arbitrary_scenario_is_rejected_before_factory(self) -> None:
        called = False

        async def factory(_config):
            nonlocal called
            called = True
            raise AssertionError("arbitrary scenario must not reach a session")

        receipt = await self.module.RealWorldAcceptanceRunner(
            env=self._env(), session_factory=factory,
        ).run("RW-ARBITRARY-999")
        self.assertEqual(receipt["status"], "SCENARIO_NOT_ALLOWLISTED")
        self.assertFalse(called)

    async def test_forbidden_recipient_rule_is_rejected(self) -> None:
        env = self._env()
        env["JARVIS_E2E_DISCORD_TARGET"] = "last contact"
        called = False

        async def factory(_config):
            nonlocal called
            called = True
            raise AssertionError("unsafe recipient must not reach a session")

        receipt = await self.module.RealWorldAcceptanceRunner(
            env=env, session_factory=factory,
        ).run("RW-DISCORD-TEST-001")
        self.assertEqual(receipt["status"], "UNSAFE_STATE")
        self.assertFalse(called)
        self.assertEqual(receipt["side_effects"]["sends"], 0)

    def test_last_contact_behavior_is_rejected_for_all_destination_kinds(self) -> None:
        for kind in ("whatsapp", "discord"):
            with self.assertRaises(self.module.OwnerSessionConfigError):
                self.module.validate_destination("most recent DM", kind)

    async def test_login_required_stops_before_any_tool_execution(self) -> None:
        module = self.module

        class Session:
            execute_calls = 0
            closed = False

            async def login_preflight(self, _service):
                return module.LoginPreflight(module.OWNER_LOGIN_REQUIRED, "owner_authentication_required")

            async def execute_tool(self, _name, _arguments):
                self.execute_calls += 1
                return object()

            async def decide_tool(self, _approval_id, _approved):
                self.execute_calls += 1
                return object()

            async def close(self):
                self.closed = True

        session = Session()

        async def factory(_config):
            return session

        async def handler(*_args):
            raise AssertionError("handler must not run before login preflight")

        receipt = await self.module.RealWorldAcceptanceRunner(
            env=self._env(), session_factory=factory,
            handlers={"RW-CHATGPT-001": handler},
        ).run("RW-CHATGPT-001")
        self.assertEqual(receipt["status"], self.module.OWNER_LOGIN_REQUIRED)
        self.assertEqual(session.execute_calls, 0)
        self.assertTrue(session.closed)
        self.assertEqual(receipt["side_effects"], {"external_writes": 0, "sends": 0})

    async def test_unknown_domain_is_rejected_without_session(self) -> None:
        env = self._env()
        env["JARVIS_E2E_NOTION_PAGE_URL"] = "https://example.invalid/jarvis-e2e"
        called = False

        async def factory(_config):
            nonlocal called
            called = True
            raise AssertionError("unknown domain must not reach a session")

        receipt = await self.module.RealWorldAcceptanceRunner(
            env=env, session_factory=factory,
        ).run("RW-NOTION-001")
        self.assertEqual(receipt["status"], "UNSAFE_STATE")
        self.assertFalse(called)

    def test_configured_targets_are_hashed_not_retained(self) -> None:
        env = self._env()
        env.update(
            {
                "JARVIS_E2E_NOTION_PAGE_URL": "https://www.notion.so/owner-dedicated-page",
                "JARVIS_E2E_SPOTIFY_QUERY": "A harmless owner-selected track",
                "JARVIS_E2E_DISCORD_TARGET": "channel:jarvis-private-e2e",
                "JARVIS_E2E_WHATSAPP_SELF_LABEL": "Message yourself",
                "JARVIS_E2E_BRAVE_PATH": r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
            }
        )
        config = self.module.load_config(env)
        blob = json.dumps(config.metadata(), ensure_ascii=False)
        for raw in (
            env["JARVIS_E2E_NOTION_PAGE_URL"],
            env["JARVIS_E2E_SPOTIFY_QUERY"],
            env["JARVIS_E2E_DISCORD_TARGET"],
            env["JARVIS_E2E_WHATSAPP_SELF_LABEL"],
            env["JARVIS_E2E_BRAVE_PATH"],
        ):
            self.assertNotIn(raw, blob)
        self.assertEqual(
            config.metadata()["discord_target"]["sha256"],
            self.module._digest(env["JARVIS_E2E_DISCORD_TARGET"]),
        )

    async def test_handler_receipt_discards_owner_content(self) -> None:
        module = self.module

        class Session:
            async def login_preflight(self, _service):
                return module.LoginPreflight(module.READY, "local_owner_runtime_ready")

            async def execute_tool(self, _name, _arguments):
                raise AssertionError("handler does not need tool execution for this projection test")

            async def decide_tool(self, _approval_id, _approved):
                raise AssertionError("handler does not need approval for this projection test")

            async def close(self):
                return None

        async def factory(_config):
            return Session()

        async def handler(*_args):
            return {
                "status": "PASS",
                "reason": "verification_complete",
                "verified": True,
                "external_writes": 1,
                "sends": 1,
                "body": "private owner content must never enter the receipt",
                "page_text": "prompt injection text must remain transient",
            }

        receipt = await self.module.RealWorldAcceptanceRunner(
            env=self._env(), session_factory=factory,
            handlers={"RW-CALC-001": handler},
        ).run("RW-CALC-001")
        blob = json.dumps(receipt, ensure_ascii=False)
        self.assertEqual(receipt["status"], "PASS")
        self.assertNotIn("private owner content", blob)
        self.assertNotIn("prompt injection text", blob)
        self.assertEqual(receipt["side_effects"], {"external_writes": 1, "sends": 1})

    def test_login_classifier_has_fail_closed_states(self) -> None:
        self.assertEqual(self.module.classify_login_state(False).status, self.module.OWNER_LOGIN_REQUIRED)
        self.assertEqual(self.module.classify_login_state(None).status, self.module.NOT_CONFIGURED)
        self.assertEqual(self.module.classify_login_state(True).status, self.module.READY)
        self.assertEqual(
            self.module.classify_login_state(True, security_challenge=True).status,
            self.module.OWNER_LOGIN_REQUIRED,
        )


class CalculatorScenarioTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = _load_runner()

    async def test_calculator_handler_uses_exact_ui_and_independent_readback(self) -> None:
        module = self.module

        class Session:
            def __init__(self) -> None:
                self.window_active = False
                self.application_open = False
                self.computer_actions: list[tuple[str, dict[str, object]]] = []
                self.tool_calls: list[tuple[str, dict[str, object]]] = []
                self.decisions: list[tuple[str, bool]] = []

            async def execute_computer_action(self, action: str, arguments: dict[str, object]):
                self.computer_actions.append((action, arguments))
                if action == "open_application":
                    self.application_open = True
                if action == "focus_window":
                    self.window_active = True
                return SimpleNamespace(status="succeeded", output={}, error_code=None, verified=True)

            async def execute_tool(self, name: str, arguments: dict[str, object]):
                self.tool_calls.append((name, arguments))
                if name == "computer.semantic.read":
                    action = arguments.get("action")
                    if action == "list_windows":
                        windows = [] if not self.application_open else [{
                            "window_ref": "window-calculator",
                            "title": "Calculator",
                            "process_name": "CalculatorApp.exe",
                            "active": self.window_active,
                        }]
                        return SimpleNamespace(
                            status="completed",
                            output={"windows": windows},
                            error_code=None,
                        )
                    if action == "find_elements":
                        control_type = arguments.get("control_type")
                        name_filter = arguments.get("name")
                        if arguments.get("automation_id") == "CalculatorResults":
                            return SimpleNamespace(
                                status="completed",
                                output={"matches": [{"element_ref": "element-display", "automation_id": "CalculatorResults"}]},
                                error_code=None,
                            )
                        if control_type == "ButtonControl":
                            refs = {
                                "Clear": "element-clear",
                                "One": "element-one",
                                "Seven": "element-seven",
                                "Multiply by": "element-multiply",
                                "Two": "element-two",
                                "Three": "element-three",
                                "Equals": "element-equals",
                            }
                            ref = refs.get(name_filter)
                            matches = [{"element_ref": ref}] if ref else []
                            return SimpleNamespace(status="completed", output={"matches": matches}, error_code=None)
                        if control_type == "TextControl":
                            return SimpleNamespace(
                                status="completed",
                                output={"matches": [{"element_ref": "element-display", "name": "391"}]},
                                error_code=None,
                            )
                    if action == "get_text":
                        return SimpleNamespace(status="completed", output={"text": "Display is 391"}, error_code=None)
                if name == "computer.semantic.act":
                    return SimpleNamespace(status="approval_required", approval_id="approval-calculator", output={}, error_code=None)
                raise AssertionError(f"unexpected tool call: {name} {arguments}")

            async def decide_tool(self, approval_id: str, approved: bool):
                self.decisions.append((approval_id, approved))
                return SimpleNamespace(status="completed", output={}, error_code=None, verified=False)

        session = Session()
        result = await module._run_calculator_scenario(
            session, "RW-CALC-001", "JARVIS_E2E_TEST_NONCE", module.OwnerSessionConfig(True, owner_id="owner", device_id="device"),
        )

        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["verified"])
        self.assertEqual([action for action, _ in session.computer_actions], ["open_application", "focus_window"])
        self.assertEqual(len(session.decisions), 7)
        self.assertTrue(all(approved for _, approved in session.decisions))

    async def test_calculator_absence_is_not_configured(self) -> None:
        module = self.module

        class Session:
            async def execute_computer_action(self, action: str, _arguments: dict[str, object]):
                self.assert_action(action)
                return SimpleNamespace(status="failed", output={}, error_code="application_not_installed")

            def assert_action(self, action: str) -> None:
                if action != "open_application":
                    raise AssertionError(f"unexpected computer action: {action}")

            async def execute_tool(self, _name: str, _arguments: dict[str, object]):
                if _name == "computer.semantic.read" and _arguments.get("action") == "list_windows":
                    return SimpleNamespace(status="completed", output={"windows": []}, error_code=None)
                raise AssertionError("missing Calculator must stop before semantic reads")

            async def decide_tool(self, _approval_id: str, _approved: bool):
                raise AssertionError("missing Calculator must stop before approval")

        result = await module._run_calculator_scenario(
            Session(), "RW-CALC-001", "JARVIS_E2E_TEST_NONCE", module.OwnerSessionConfig(True, owner_id="owner", device_id="device"),
        )

        self.assertEqual(result["status"], module.NOT_CONFIGURED)
        self.assertEqual(result["reason"], "calculator_not_configured")
        self.assertFalse(result["verified"])

    async def test_calculator_handler_targets_new_window_around_stale_exact_windows(self) -> None:
        module = self.module

        class Session:
            def __init__(self) -> None:
                self.opened = False
                self.focused_ref: str | None = None
                self.decisions: list[str] = []

            async def execute_computer_action(self, action: str, arguments: dict[str, object]):
                if action == "open_application":
                    self.opened = True
                    return SimpleNamespace(status="succeeded", output={}, error_code=None, verified=True)
                if action == "focus_window":
                    self.focused_ref = str(arguments["window_ref"])
                    return SimpleNamespace(status="succeeded", output={}, error_code=None, verified=True)
                raise AssertionError(f"unexpected computer action: {action}")

            async def execute_tool(self, name: str, arguments: dict[str, object]):
                if name == "computer.semantic.read":
                    action = arguments.get("action")
                    if action == "list_windows":
                        windows = [
                            {"window_ref": "window-old-1", "title": "Calculator", "process_name": "ApplicationFrameHost.exe", "active": False},
                            {"window_ref": "window-old-2", "title": "Calculator", "process_name": "ApplicationFrameHost.exe", "active": False},
                        ]
                        if self.opened:
                            windows.append({"window_ref": "window-new", "title": "Calculator", "process_name": "ApplicationFrameHost.exe", "active": True})
                        return SimpleNamespace(status="completed", output={"windows": windows}, error_code=None)
                    if action == "find_elements":
                        control_type = arguments.get("control_type")
                        if arguments.get("automation_id") == "CalculatorResults":
                            return SimpleNamespace(status="completed", output={"matches": [{"element_ref": "element-display"}]}, error_code=None)
                        if control_type == "ButtonControl":
                            refs = {
                                "Clear": "element-clear",
                                "One": "element-one",
                                "Seven": "element-seven",
                                "Multiply by": "element-multiply",
                                "Two": "element-two",
                                "Three": "element-three",
                                "Equals": "element-equals",
                            }
                            ref = refs.get(arguments.get("name"))
                            return SimpleNamespace(status="completed", output={"matches": [{"element_ref": ref}] if ref else []}, error_code=None)
                        if control_type == "TextControl":
                            return SimpleNamespace(status="completed", output={"matches": [{"element_ref": "element-display"}]}, error_code=None)
                    if action == "get_text":
                        return SimpleNamespace(status="completed", output={"text": "391"}, error_code=None)
                if name == "computer.semantic.act":
                    return SimpleNamespace(status="approval_required", approval_id=f"approval-{len(self.decisions)}", output={}, error_code=None)
                raise AssertionError(f"unexpected tool call: {name} {arguments}")

            async def decide_tool(self, approval_id: str, approved: bool):
                if not approved:
                    raise AssertionError("Calculator invoke must be explicitly approved")
                self.decisions.append(approval_id)
                return SimpleNamespace(status="completed", output={}, error_code=None, verified=False)

        session = Session()
        result = await module._run_calculator_scenario(
            session, "RW-CALC-001", "JARVIS_E2E_TEST_NONCE", module.OwnerSessionConfig(True, owner_id="owner", device_id="device"),
        )

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(session.focused_ref, "window-new")
        self.assertEqual(len(session.decisions), 7)

    async def test_calculator_handler_settles_launch_before_grounding_exact_window(self) -> None:
        module = self.module

        class Session:
            def __init__(self) -> None:
                self.opened = False
                self.settled = False
                self.focused_ref: str | None = None
                self.sleep_delays: list[float] = []
                self.decisions = 0

            async def execute_computer_action(self, action: str, arguments: dict[str, object]):
                if action == "open_application":
                    self.opened = True
                    return SimpleNamespace(status="succeeded", output={}, error_code=None, verified=True)
                if action == "focus_window":
                    self.focused_ref = str(arguments["window_ref"])
                    return SimpleNamespace(status="succeeded", output={}, error_code=None, verified=True)
                raise AssertionError(f"unexpected computer action: {action}")

            async def execute_tool(self, name: str, arguments: dict[str, object]):
                if name == "computer.semantic.read":
                    action = arguments.get("action")
                    if action == "list_windows":
                        windows = [
                            {"window_ref": "window-old-1", "title": "Calculator", "process_name": "ApplicationFrameHost.exe", "active": False},
                            {"window_ref": "window-old-2", "title": "Calculator", "process_name": "ApplicationFrameHost.exe", "active": False},
                        ]
                        if self.opened and self.settled:
                            windows.append({"window_ref": "window-new", "title": "Calculator", "process_name": "ApplicationFrameHost.exe", "active": True})
                        else:
                            windows.append({"window_ref": "window-old-active", "title": "Calculator", "process_name": "ApplicationFrameHost.exe", "active": True})
                        if action == "list_windows":
                            return SimpleNamespace(status="completed", output={"windows": windows}, error_code=None)
                    if action == "find_elements":
                        control_type = arguments.get("control_type")
                        if arguments.get("automation_id") == "CalculatorResults":
                            return SimpleNamespace(status="completed", output={"matches": [{"element_ref": "element-display"}]}, error_code=None)
                        if control_type == "ButtonControl":
                            refs = {
                                "Clear": "element-clear",
                                "One": "element-one",
                                "Seven": "element-seven",
                                "Multiply by": "element-multiply",
                                "Two": "element-two",
                                "Three": "element-three",
                                "Equals": "element-equals",
                            }
                            ref = refs.get(arguments.get("name"))
                            return SimpleNamespace(status="completed", output={"matches": [{"element_ref": ref}] if ref else []}, error_code=None)
                        if control_type == "TextControl":
                            return SimpleNamespace(status="completed", output={"matches": [{"element_ref": "element-display"}]}, error_code=None)
                    if action == "get_text":
                        return SimpleNamespace(status="completed", output={"text": "391"}, error_code=None)
                if name == "computer.semantic.act":
                    self.decisions += 1
                    return SimpleNamespace(status="approval_required", approval_id=f"approval-{self.decisions}", output={}, error_code=None)
                raise AssertionError(f"unexpected tool call: {name} {arguments}")

            async def decide_tool(self, _approval_id: str, approved: bool):
                if not approved:
                    raise AssertionError("Calculator invoke must be explicitly approved")
                return SimpleNamespace(status="completed", output={}, error_code=None, verified=False)

        session = Session()

        async def settle(delay: float) -> None:
            session.sleep_delays.append(delay)
            session.settled = True

        with patch.object(module.asyncio, "sleep", new=settle):
            result = await module._run_calculator_scenario(
                session, "RW-CALC-001", "JARVIS_E2E_TEST_NONCE", module.OwnerSessionConfig(True, owner_id="owner", device_id="device"),
            )

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(session.focused_ref, "window-new")
        self.assertEqual(session.sleep_delays, [module._CALCULATOR_POST_LAUNCH_SETTLE_SECONDS])
        self.assertEqual(session.decisions, 7)

    async def test_calculator_handler_refuses_exact_window_ambiguity_before_input(self) -> None:
        module = self.module

        class Session:
            def __init__(self) -> None:
                self.input_calls = 0

            async def execute_computer_action(self, action: str, _arguments: dict[str, object]):
                if action == "open_application":
                    return SimpleNamespace(status="succeeded", output={}, error_code=None, verified=True)
                if action == "focus_window":
                    raise AssertionError("ambiguous Calculator windows must not be focused")
                raise AssertionError(f"unexpected computer action: {action}")

            async def execute_tool(self, name: str, arguments: dict[str, object]):
                if name == "computer.semantic.read" and arguments.get("action") == "list_windows":
                    return SimpleNamespace(
                        status="completed",
                        output={
                            "windows": [
                                {"window_ref": "window-calculator-1", "title": "Calculator", "process_name": "CalculatorApp.exe", "active": False},
                                {"window_ref": "window-calculator-2", "title": "Calculator", "process_name": "CalculatorApp.exe", "active": False},
                            ],
                        },
                        error_code=None,
                    )
                self.input_calls += 1
                raise AssertionError("ambiguous window must stop before semantic input")

            async def decide_tool(self, _approval_id: str, _approved: bool):
                self.input_calls += 1
                raise AssertionError("ambiguous window must stop before approval")

        result = await module._run_calculator_scenario(
            Session(), "RW-CALC-001", "JARVIS_E2E_TEST_NONCE", module.OwnerSessionConfig(True, owner_id="owner", device_id="device"),
        )

        self.assertEqual(result["status"], "FAILED")
        self.assertFalse(result["verified"])
        self.assertEqual(result.get("sends", 0), 0)


class BraveHostScenarioTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = _load_runner()

    async def test_brave_host_baseline_stops_at_browser_v2_boundary(self) -> None:
        module = self.module
        path = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"

        class Session:
            def __init__(self) -> None:
                self.actions: list[tuple[str, dict[str, object]]] = []
                self.tool_calls: list[tuple[str, dict[str, object]]] = []
                self.closed = False

            async def login_preflight(self, service: str):
                self.tool_calls.append(("login_preflight", {"service": service}))
                return module.LoginPreflight(module.READY, "local_owner_runtime_ready")

            async def execute_computer_action(self, action: str, arguments: dict[str, object]):
                self.actions.append((action, arguments))
                if action == "open_application":
                    return SimpleNamespace(status="succeeded", output={"application": "brave", "executable": path}, error_code=None, verified=True)
                if action == "focus_window":
                    return SimpleNamespace(status="succeeded", output={}, error_code=None, verified=True)
                raise AssertionError(f"unexpected computer action: {action}")

            async def execute_tool(self, name: str, arguments: dict[str, object]):
                self.tool_calls.append((name, arguments))
                if name == "computer.semantic.read" and arguments.get("action") == "list_windows":
                    return SimpleNamespace(
                        status="completed",
                        output={"windows": [{"window_ref": "window-brave", "title": "Owner Brave", "process_name": "brave.exe", "active": True}]},
                        error_code=None,
                    )
                raise AssertionError("host baseline must not use browser or web tools")

            async def decide_tool(self, _approval_id: str, _approved: bool):
                raise AssertionError("host baseline must not request approval")

            async def close(self):
                self.closed = True

        session = Session()
        before_path = os.environ.get("PATH")

        async def no_sleep(_delay: float) -> None:
            return None

        async def factory(_config):
            return session

        env = {
            module.ENABLE_ENV: "1",
            "JARVIS_E2E_OWNER_ID": "owner-test",
            "JARVIS_E2E_DEVICE_ID": "device-test",
            "JARVIS_E2E_BRAVE_PATH": path,
        }
        with patch.object(module.asyncio, "sleep", new=no_sleep):
            receipt = await module.RealWorldAcceptanceRunner(env=env, session_factory=factory).run("RW-BRAVE-001", runs=1)

        self.assertEqual(receipt["status"], "PARTIAL")
        self.assertEqual(receipt["results"][0]["reason"], "cross_workstream_blocker_browser_v2_required")
        self.assertTrue(receipt["results"][0]["host_baseline"])
        self.assertFalse(receipt["results"][0]["verified"])
        self.assertEqual([action for action, _ in session.actions], ["open_application", "focus_window"])
        self.assertEqual(session.tool_calls[0], ("login_preflight", {"service": "brave_host"}))
        self.assertTrue(session.closed)
        self.assertEqual(os.environ.get("PATH"), before_path)

    async def test_brave_host_restores_an_unset_process_path(self) -> None:
        module = self.module
        path = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"

        class Session:
            async def login_preflight(self, _service: str):
                return module.LoginPreflight(module.READY, "local_owner_runtime_ready")

            async def execute_computer_action(self, action: str, _arguments: dict[str, object]):
                if action == "open_application":
                    return SimpleNamespace(status="failed", output={}, error_code="application_not_installed", verified=False)
                raise AssertionError(f"unexpected computer action: {action}")

            async def execute_tool(self, _name: str, _arguments: dict[str, object]):
                raise AssertionError("failed launch must stop before semantic reads")

            async def decide_tool(self, _approval_id: str, _approved: bool):
                raise AssertionError("failed launch must not request approval")

            async def close(self):
                return None

        async def factory(_config):
            return Session()

        env = {
            module.ENABLE_ENV: "1",
            "JARVIS_E2E_OWNER_ID": "owner-test",
            "JARVIS_E2E_DEVICE_ID": "device-test",
            "JARVIS_E2E_BRAVE_PATH": path,
        }
        with patch.dict(os.environ, {}, clear=True):
            receipt = await module.RealWorldAcceptanceRunner(env=env, session_factory=factory).run("RW-BRAVE-001", runs=1)

            self.assertNotIn("PATH", os.environ)
        self.assertEqual(receipt["status"], module.NOT_CONFIGURED)
        self.assertEqual(receipt["results"][0]["reason"], "brave_path_not_found")

    async def test_brave_host_refuses_multiple_inactive_windows_before_focus(self) -> None:
        module = self.module
        path = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"

        class Session:
            def __init__(self) -> None:
                self.actions: list[str] = []

            async def login_preflight(self, _service: str):
                return module.LoginPreflight(module.READY, "local_owner_runtime_ready")

            async def execute_computer_action(self, action: str, _arguments: dict[str, object]):
                self.actions.append(action)
                if action == "open_application":
                    return SimpleNamespace(status="succeeded", output={"executable": path}, error_code=None, verified=True)
                raise AssertionError("ambiguous host grounding must stop before focus")

            async def execute_tool(self, name: str, arguments: dict[str, object]):
                if name == "computer.semantic.read" and arguments.get("action") == "list_windows":
                    return SimpleNamespace(
                        status="completed",
                        output={
                            "windows": [
                                {"window_ref": "window-brave-a", "title": "New Tab - Brave", "process_name": "brave.exe", "active": False},
                                {"window_ref": "window-brave-b", "title": "New Tab - Brave", "process_name": "brave.exe", "active": False},
                            ],
                        },
                        error_code=None,
                    )
                raise AssertionError("ambiguous host grounding must use only window listing")

            async def decide_tool(self, _approval_id: str, _approved: bool):
                raise AssertionError("host baseline must not request approval")

            async def close(self):
                return None

        session = Session()

        async def factory(_config):
            return session

        env = {
            module.ENABLE_ENV: "1",
            "JARVIS_E2E_OWNER_ID": "owner-test",
            "JARVIS_E2E_DEVICE_ID": "device-test",
            "JARVIS_E2E_BRAVE_PATH": path,
        }
        receipt = await module.RealWorldAcceptanceRunner(env=env, session_factory=factory).run("RW-BRAVE-001", runs=1)

        self.assertEqual(receipt["status"], "PARTIAL")
        self.assertEqual(receipt["results"][0]["reason"], "brave_window_ambiguous")
        self.assertFalse(receipt["results"][0]["host_baseline"])
        self.assertEqual(session.actions, ["open_application"])


class BraveLauncherTests(unittest.TestCase):
    def test_brave_launcher_uses_allowlisted_name_and_shell_false(self) -> None:
        controller = WindowsNativeComputerController.__new__(WindowsNativeComputerController)
        path = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
        with patch("jarvis.computer.service.resolve_standard_application_target", return_value=Path(path)) as resolver:
            with patch("jarvis.computer.service.subprocess.Popen") as popen:
                result = controller._open_application({"application": "brave"})

        self.assertEqual(result.status, "succeeded")
        self.assertTrue(result.verified)
        resolver.assert_called_once_with("brave")
        popen.assert_called_once_with([path, "--new-window"], shell=False, close_fds=True)


class ProductionSessionTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = _load_runner()

    async def test_existing_owner_id_resolves_owner_identity_before_session(self) -> None:
        module = self.module

        class IdentityService:
            def __init__(self) -> None:
                self.identity_lookup: str | None = None
                self.device_lookup: str | None = None

            async def get_identity(self, identity_id: str):
                self.identity_lookup = identity_id
                if identity_id != "identity-owner":
                    return None
                return SimpleNamespace(identity_id=identity_id, owner_id="owner")

            async def device(self, device_id: str):
                self.device_lookup = device_id
                return SimpleNamespace(owner_id="owner")

        class Runtime:
            def __init__(self) -> None:
                self.state = SimpleNamespace(value="ready")
                self.identity = IdentityService()
                self.repository = SimpleNamespace(
                    first_identity=lambda owner_id: {"id": "identity-owner", "owner_id": owner_id},
                )
                self.shutdown_calls = 0

            async def start(self) -> None:
                return None

            async def shutdown(self) -> None:
                self.shutdown_calls += 1

        runtime = Runtime()
        with patch("jarvis.bootstrap.create_runtime", return_value=runtime) as create_runtime:
            with patch("jarvis.config.JarvisConfig.from_env", return_value=SimpleNamespace()) as from_env:
                session = await module._new_production_session(
                    module.OwnerSessionConfig(True, owner_id="owner", device_id="device"),
                )

        self.assertIsInstance(session, module.ProductionToolSession)
        self.assertEqual(runtime.identity.identity_lookup, "identity-owner")
        self.assertEqual(runtime.identity.device_lookup, "device")
        create_runtime.assert_called_once()
        from_env.assert_called_once()
        await session.close()
        self.assertEqual(runtime.shutdown_calls, 1)
