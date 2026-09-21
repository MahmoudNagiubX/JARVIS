from __future__ import annotations

import unittest
from dataclasses import dataclass

from jarvis.agents.routing.native_app_fast_path import NativeAppFastPath
from jarvis.authority.identity.service import EnrollmentGrant
from jarvis.bootstrap import create_runtime
from jarvis.config import JarvisConfig
from jarvis.computer.applications import ApplicationLookup
from jarvis.contracts import ComputerAction, ToolContext, ToolResult, ToolResultStatus


@dataclass(frozen=True, slots=True)
class _Application:
    app_ref: str
    display_name: str
    risk_class: str = "user"


class _Registry:
    def __init__(self) -> None:
        self.notion = _Application("app-notion-test", "Notion")

    def find(self, query: str, *, refresh: bool = False) -> ApplicationLookup:
        del refresh
        if query.casefold().strip() == "notion":
            return ApplicationLookup("matched", self.notion, (self.notion,))
        return ApplicationLookup("not_found", reason="application_not_found")


class _RecordingController:
    def __init__(self, registry: _Registry) -> None:
        self.application_registry = registry
        self.actions: list[tuple[ComputerAction, ToolContext]] = []

    async def execute(self, action: ComputerAction, context: ToolContext) -> ToolResult:
        self.actions.append((action, context))
        timing = context.metadata.get("_native_action_timing")
        if callable(timing):
            timing("launch_dispatched")
        return ToolResult(ToolResultStatus.SUCCEEDED, {"display_name": "Notion"}, verified=True)


class _NoModelCalls:
    async def generate(self, request, route):
        del request, route
        raise AssertionError("native app fast path must not call a model")


class NativeAppFastPathTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:"))
        await self.runtime.start()
        self.identity = await self.runtime.identity.bootstrap_owner("Native Action Owner")
        grant = await self.runtime.identity.create_enrollment(
            EnrollmentGrant(
                self.identity.owner_id,
                "Native Action Desktop",
                "desktop",
                "windows",
                ("tool.request",),
                ("computer.observe", "computer.input"),
            )
        )
        issued = await self.runtime.identity.redeem_enrollment(grant.code)
        self.device = await self.runtime.identity.authenticate(issued.raw, issued.device_id)
        assert self.device is not None
        self.registry = _Registry()
        self.controller = _RecordingController(self.registry)
        self.runtime.computer_actions.controller.local = self.controller
        self.runtime.agent.models = _NoModelCalls()
        self.runtime.agent.native_app_fast_path = NativeAppFastPath(self.registry, self.runtime.tool_service)

    async def asyncTearDown(self) -> None:
        await self.runtime.shutdown()

    async def test_exact_english_command_uses_canonical_tool_path_without_model(self) -> None:
        outcome = await self.runtime.agent.process_text("Open Notion", self.identity, self.device)

        self.assertEqual(outcome.state.value, "succeeded")
        self.assertEqual(outcome.response, "Notion opened. Verified.")
        self.assertEqual(len(self.controller.actions), 1)
        self.assertEqual(dict(self.controller.actions[0][0].parameters), {"app_ref": "app-notion-test"})
        events = self.runtime.repository.database.connection.execute(
            "SELECT payload_json FROM events WHERE event_type = 'run.completed' ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        self.assertIsNotNone(events)
        payload = str(events[0])
        for stage in (
            "request_received",
            "intent_classified",
            "app_ref_resolved",
            "authority_decided",
            "launch_dispatched",
            "verification_completed",
        ):
            self.assertIn(stage, payload)

    async def test_arabic_command_uses_the_same_narrow_path(self) -> None:
        outcome = await self.runtime.agent.process_text("افتح Notion", self.identity, self.device)

        self.assertEqual(outcome.state.value, "succeeded")
        self.assertEqual(outcome.response, "Notion opened. Verified.")
        self.assertEqual(len(self.controller.actions), 1)

    async def test_compound_command_is_not_guessed_by_the_fast_path(self) -> None:
        fast_path = self.runtime.agent.native_app_fast_path
        assert fast_path is not None
        self.assertIsNone(fast_path.classify("Open Notion and Spotify"))
        self.assertIsNone(fast_path.classify("Open and read this page"))
        self.assertIsNone(fast_path.classify("افتح Notion و Spotify"))

    async def test_not_found_app_is_handled_truthfully_without_a_model_call(self) -> None:
        outcome = await self.runtime.agent.process_text("Launch Spotify", self.identity, self.device)

        self.assertEqual(outcome.state.value, "failed")
        self.assertEqual(outcome.response, "Spotify did not open.")
        self.assertEqual(len(self.controller.actions), 0)


if __name__ == "__main__":
    unittest.main()
