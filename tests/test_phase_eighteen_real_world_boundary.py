"""Batch 09 T1 boundary and privacy tests.

These tests exercise only the opt-in dispatcher and injected session seam. They
never start a runtime, open an application, authenticate a service, or send a
message.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


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
                self.computer_actions: list[tuple[str, dict[str, object]]] = []
                self.tool_calls: list[tuple[str, dict[str, object]]] = []
                self.decisions: list[tuple[str, bool]] = []

            async def execute_computer_action(self, action: str, arguments: dict[str, object]):
                self.computer_actions.append((action, arguments))
                if action == "focus_window":
                    self.window_active = True
                return SimpleNamespace(status="succeeded", output={}, error_code=None, verified=True)

            async def execute_tool(self, name: str, arguments: dict[str, object]):
                self.tool_calls.append((name, arguments))
                if name == "computer.semantic.read":
                    action = arguments.get("action")
                    if action == "list_windows":
                        return SimpleNamespace(
                            status="completed",
                            output={
                                "windows": [{
                                    "window_ref": "window-calculator",
                                    "title": "Calculator",
                                    "process_name": "CalculatorApp.exe",
                                    "active": self.window_active,
                                }],
                            },
                            error_code=None,
                        )
                    if action == "find_elements":
                        control_type = arguments.get("control_type")
                        name_filter = arguments.get("name")
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
                        return SimpleNamespace(status="completed", output={"text": "391"}, error_code=None)
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
