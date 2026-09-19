"""Phase 18A.2 stabilization fixes: F18A1-003, F18A1-001, F18A1-002, F18A1-009, F18A1-007, F18A1-012."""

from __future__ import annotations

import asyncio
import json
import unittest
import unittest.mock

from jarvis.agents.runtime.runtime import AgentRuntime
from jarvis.authority.identity.service import EnrollmentGrant
from jarvis.bootstrap import create_runtime
from jarvis.browser.service import LocalBrowserController
from jarvis.config import JarvisConfig
from jarvis.contracts import (
    ComputerAction,
    DeviceEnrollmentRequest,
    HomeAction,
    HomeEntityMapping,
    ToolContext,
    ToolResult,
    ToolResultRetention,
    ToolResultStatus,
)
from jarvis.devices.home.service import HomeActionService, HomeAssistantTransport, RestrictedMQTTTransport
from jarvis.tools.registry import ToolSpec


class PhaseEighteenStabilizationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:"))
        await self.runtime.start()
        self.identity = await self.runtime.identity.bootstrap_owner("Phase Eighteen Owner")
        enrollment = await self.runtime.identity.create_enrollment(
            EnrollmentGrant(
                self.identity.owner_id,
                "Phase Eighteen Device",
                "desktop",
                "windows",
                ("tool.request",),
                ("computer.observe", "computer.input", "home.read", "home.control"),
            )
        )
        issued = await self.runtime.identity.redeem_enrollment(enrollment.code)
        self.device = await self.runtime.identity.authenticate(issued.raw, issued.device_id)
        assert self.device is not None

    async def asyncTearDown(self) -> None:
        await self.runtime.shutdown()

    # -- F18A1-003: verification truth must reach the model-facing tool message --

    async def test_verified_true_reaches_model_visible_tool_result(self) -> None:
        session = self.runtime.repository.create_session(self.identity.owner_id, self.device.device_id)
        context = ToolContext(self.identity, self.device, session.id, "correlation-verified-true")
        result = await self.runtime.tool_service.execute("status.read", {}, context)
        self.assertEqual(result.status.value, "completed")
        self.assertTrue(result.verified)
        message = AgentRuntime._bounded_tool_message(result.output, result.error_code, result.verified)
        self.assertTrue(json.loads(message)["verified"])

    async def test_verified_false_reaches_model_visible_tool_result(self) -> None:
        # Any tool name outside the explicit allow-list falls through to the generic
        # "tool." catch-all rule, which requires approval regardless of risk_level -
        # so this exercises the approval-resume path too (see tools/service.py rules).
        def _unverified_handler(arguments: dict, _context: ToolContext) -> ToolResult:
            return ToolResult(ToolResultStatus.SUCCEEDED, {"echo": arguments["payload"]}, verified=False)

        self.runtime.tools.register(
            ToolSpec(
                "tool-test-unverified-v1", "test.unverified.action", "1", "Test-only unverified fixture.",
                "safe", "tool.request", frozenset(), 5.0, True, _unverified_handler,
                parameters_schema={
                    "type": "object",
                    "properties": {"payload": {"type": "string", "maxLength": 200}},
                    "required": ["payload"],
                    "additionalProperties": False,
                },
            )
        )
        session = self.runtime.repository.create_session(self.identity.owner_id, self.device.device_id)
        context = ToolContext(self.identity, self.device, session.id, "correlation-verified-false")
        requested = await self.runtime.tool_service.execute("test.unverified.action", {"payload": "hello"}, context)
        self.assertEqual(requested.status.value, "approval_required")
        assert requested.approval_id is not None
        result = await self.runtime.tool_service.decide_and_resume(requested.approval_id, True, self.identity.identity_id, context)
        self.assertEqual(result.status.value, "completed")
        self.assertFalse(result.verified)
        message = AgentRuntime._bounded_tool_message(result.output, result.error_code, result.verified)
        parsed = json.loads(message)
        self.assertFalse(parsed["verified"])
        self.assertEqual(parsed["echo"], "hello")

    async def test_durable_approval_claim_prevents_concurrent_handler_replay(self) -> None:
        calls: list[str] = []

        async def _durable_handler(arguments: dict, _context: ToolContext) -> ToolResult:
            calls.append(str(arguments["payload"]))
            await asyncio.sleep(0)
            return ToolResult(ToolResultStatus.SUCCEEDED, {"payload": arguments["payload"]}, verified=True)

        self.runtime.tools.register(
            ToolSpec(
                "tool-test-durable-once-v1", "test.durable.once", "1", "Test-only durable approval fixture.",
                "safe", "tool.request", frozenset(), 5.0, False, _durable_handler,
                parameters_schema={
                    "type": "object",
                    "properties": {"payload": {"type": "string", "maxLength": 200}},
                    "required": ["payload"],
                    "additionalProperties": False,
                },
            )
        )
        session = self.runtime.repository.create_session(self.identity.owner_id, self.device.device_id)
        context = ToolContext(self.identity, self.device, session.id, "correlation-durable-once")
        requested = await self.runtime.tool_service.execute("test.durable.once", {"payload": "one-shot"}, context)
        self.assertEqual(requested.status.value, "approval_required")
        assert requested.approval_id is not None

        first, second = await asyncio.gather(
            self.runtime.tool_service.decide_and_resume(requested.approval_id, True, self.identity.identity_id, context),
            self.runtime.tool_service.decide_and_resume(requested.approval_id, True, self.identity.identity_id, context),
        )

        self.assertEqual(sum(result.status.value == "completed" for result in (first, second)), 1)
        replay = second if first.status.value == "completed" else first
        self.assertEqual(replay.status.value, "failed")
        self.assertEqual(replay.error_code, "approval_already_decided")
        self.assertEqual(calls, ["one-shot"])

    def test_bounded_tool_message_error_handling_and_backward_compatibility_are_preserved(self) -> None:
        # No verified argument (existing call shape): behavior must be byte-identical to before this fix.
        output = {
            "context": {
                "active_window": {"process_name": "active-app.exe", "title": "JARVIS"},
                "windows": [{"process_name": f"background-{index}.exe", "title": "x" * 300} for index in range(50)],
            },
        }
        legacy = AgentRuntime._bounded_tool_message(output)
        self.assertLessEqual(len(legacy), AgentRuntime.MAX_TOOL_MESSAGE_CHARS)
        self.assertIn("active-app.exe", legacy)
        self.assertNotIn("verified", json.loads(legacy))

        # verified survives truncation of an oversized tool result.
        truncated = AgentRuntime._bounded_tool_message({"huge": "x" * 10000}, verified=False)
        self.assertLessEqual(len(truncated), AgentRuntime.MAX_TOOL_MESSAGE_CHARS)
        parsed = json.loads(truncated)
        self.assertTrue(parsed["truncated"])
        self.assertFalse(parsed["verified"])

        # A non-dict tool output is wrapped rather than dropped.
        wrapped = json.loads(AgentRuntime._bounded_tool_message(["a", "b"], verified=True))
        self.assertEqual(wrapped["result"], ["a", "b"])
        self.assertTrue(wrapped["verified"])

        # A failed tool call with an error_code and no verified evidence stays unaffected.
        failed = json.loads(AgentRuntime._bounded_tool_message(None, "executor_error"))
        self.assertEqual(failed["error"], "executor_error")
        self.assertNotIn("verified", failed)

    async def test_ephemeral_argument_and_output_redaction_is_unaffected_by_verified_propagation(self) -> None:
        def _ephemeral_handler(arguments: dict, _context: ToolContext) -> ToolResult:
            return ToolResult(ToolResultStatus.SUCCEEDED, {"echo": arguments["payload"]}, verified=False)

        self.runtime.tools.register(
            ToolSpec(
                "tool-test-ephemeral-unverified-v1", "test.ephemeral.unverified", "1", "Test-only ephemeral fixture.",
                "safe", "tool.request", frozenset(), 5.0, True, _ephemeral_handler,
                parameters_schema={
                    "type": "object",
                    "properties": {"payload": {"type": "string", "maxLength": 200}},
                    "required": ["payload"],
                    "additionalProperties": False,
                },
                retention=ToolResultRetention.EPHEMERAL,
                argument_retention=ToolResultRetention.EPHEMERAL,
            )
        )
        session = self.runtime.repository.create_session(self.identity.owner_id, self.device.device_id)
        context = ToolContext(self.identity, self.device, session.id, "correlation-ephemeral")
        secret_payload = "sensitive-value-should-never-be-persisted"
        requested = await self.runtime.tool_service.execute("test.ephemeral.unverified", {"payload": secret_payload}, context)
        self.assertEqual(requested.status.value, "approval_required")
        assert requested.approval_id is not None
        result = await self.runtime.tool_service.decide_and_resume(requested.approval_id, True, self.identity.identity_id, context)
        self.assertEqual(result.status.value, "completed")
        self.assertFalse(result.verified)

        # The live model-facing message legitimately carries the tool's own output plus the new verified field.
        message = AgentRuntime._bounded_tool_message(result.output, result.error_code, result.verified)
        self.assertIn(secret_payload, message)
        self.assertFalse(json.loads(message)["verified"])

        # But durable persistence must remain redacted exactly as before this fix.
        row = self.runtime.repository.tool_call(result.tool_call_id)
        assert row is not None
        self.assertNotIn(secret_payload, row["arguments_json"])
        self.assertNotIn(secret_payload, row["output_json"] or "")

    # -- F18A1-001: device revocation must fail truthfully, never claim false success --

    async def test_device_revocation_propagates_credential_failure_and_reports_no_false_success(self) -> None:
        ticket = await self.runtime.device_fabric.issue_enrollment_ticket(self.identity.owner_id, "Stabilization Satellite")
        enrolled = await self.runtime.device_fabric.enroll_device(
            DeviceEnrollmentRequest(ticket.code, "stabilization-device-1", "Stabilization Satellite", "windows")
        )
        self.assertTrue(enrolled.accepted)
        device_id = enrolled.device_id
        assert device_id is not None

        original_revoke_device = self.runtime.repository.revoke_device

        def _failing_revoke_device(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("simulated_credential_revocation_failure")

        self.runtime.repository.revoke_device = _failing_revoke_device  # type: ignore[method-assign]
        try:
            with self.assertRaises(RuntimeError):
                await self.runtime.device_fabric.revoke(self.identity.owner_id, device_id)
        finally:
            self.runtime.repository.revoke_device = original_revoke_device  # type: ignore[method-assign]

        current = await self.runtime.device_fabric.get(self.identity.owner_id, device_id)
        self.assertIsNotNone(current)
        self.assertNotEqual(current.status, "revoked")
        self.assertFalse(any(row["event_type"] == "device.revoked" for row in self.runtime.repository.events()))
        self.assertFalse(any(row["event_type"] == "device.revoked" for row in self.runtime.repository.audit()))

        # Happy path keeps working once the transient failure is gone.
        revoked = await self.runtime.device_fabric.revoke(self.identity.owner_id, device_id)
        self.assertEqual(revoked.status, "revoked")
        self.assertTrue(any(row["event_type"] == "device.revoked" for row in self.runtime.repository.events()))

    async def test_device_revocation_happy_path_still_succeeds(self) -> None:
        ticket = await self.runtime.device_fabric.issue_enrollment_ticket(self.identity.owner_id, "Stabilization Satellite 2")
        enrolled = await self.runtime.device_fabric.enroll_device(
            DeviceEnrollmentRequest(ticket.code, "stabilization-device-2", "Stabilization Satellite 2", "windows")
        )
        assert enrolled.device_id is not None
        revoked = await self.runtime.device_fabric.revoke(self.identity.owner_id, enrolled.device_id)
        self.assertEqual(revoked.status, "revoked")
        # Revoking an already-revoked device remains idempotent (unchanged behavior).
        again = await self.runtime.device_fabric.revoke(self.identity.owner_id, enrolled.device_id)
        self.assertEqual(again.status, "revoked")

    # -- F18A1-002 / F18A1-009: Home Assistant verification must be independent and degrade truthfully --

    async def test_home_assistant_reports_verified_only_after_matching_independent_readback(self) -> None:
        def fake_request(method: str, url: str, _body: bytes | None, _headers: dict) -> tuple[int, bytes]:
            if method == "POST" and url.endswith("/api/services/light/turn_on"):
                return 200, b"{}"
            if method == "GET" and url.endswith("/api/states/light.office"):
                return 200, json.dumps({"state": "on", "attributes": {}}).encode("utf-8")
            raise AssertionError(f"unexpected call {method} {url}")

        transport = HomeAssistantTransport(request=fake_request)
        result = await transport.execute(HomeAction("light.office", "turn_on", dry_run=False))
        self.assertEqual(result.status, "succeeded")
        self.assertTrue(result.verified)

    async def test_home_assistant_does_not_claim_verified_when_state_does_not_change(self) -> None:
        def fake_request(method: str, _url: str, _body: bytes | None, _headers: dict) -> tuple[int, bytes]:
            if method == "POST":
                return 200, b"{}"
            return 200, json.dumps({"state": "off", "attributes": {}}).encode("utf-8")

        transport = HomeAssistantTransport(request=fake_request)
        result = await transport.execute(HomeAction("light.office", "turn_on", dry_run=False))
        # HTTP acceptance alone is never proof; the actual state contradicts the intended effect.
        self.assertEqual(result.status, "succeeded")
        self.assertFalse(result.verified)

    async def test_home_assistant_does_not_claim_verified_when_readback_unavailable(self) -> None:
        def fake_request(method: str, _url: str, _body: bytes | None, _headers: dict) -> tuple[int, bytes]:
            if method == "POST":
                return 200, b"{}"
            return 503, b""

        transport = HomeAssistantTransport(request=fake_request)
        result = await transport.execute(HomeAction("light.office", "turn_on", dry_run=False))
        self.assertEqual(result.status, "succeeded")
        self.assertFalse(result.verified)

    async def test_home_assistant_unverifiable_action_is_reported_truthfully(self) -> None:
        def fake_request(method: str, _url: str, _body: bytes | None, _headers: dict) -> tuple[int, bytes]:
            if method == "POST":
                return 200, b"{}"
            raise AssertionError("a scene trigger must not attempt a generic state read-back")

        transport = HomeAssistantTransport(request=fake_request)
        result = await transport.execute(HomeAction("scene.movie_night", "trigger_scene", dry_run=False))
        self.assertEqual(result.status, "succeeded")
        self.assertFalse(result.verified)

    async def test_home_assistant_write_provider_exception_degrades_truthfully_at_transport_level(self) -> None:
        def failing_request(_method: str, _url: str, _body: bytes | None, _headers: dict) -> tuple[int, bytes]:
            raise OSError("connection refused")

        transport = HomeAssistantTransport(request=failing_request)
        result = await transport.execute(HomeAction("light.office", "turn_on", dry_run=False))
        self.assertEqual(result.status, "failed")
        self.assertFalse(result.verified)
        assert result.error_code is not None
        self.assertTrue(result.error_code.startswith("home_assistant_unreachable"))

    async def test_home_action_service_boundary_never_leaks_uncaught_provider_exception(self) -> None:
        def failing_request(_method: str, _url: str, _body: bytes | None, _headers: dict) -> tuple[int, bytes]:
            raise OSError("connection refused")

        transport = HomeAssistantTransport(request=failing_request)
        home = HomeActionService(
            transport, self.runtime.repository, self.runtime.event_bus,
            self.runtime.permission, self.runtime.audit, RestrictedMQTTTransport(), approval=self.runtime.approval,
        )
        home.register_entity_mapping(HomeEntityMapping("light.office"))
        result = await home.execute(HomeAction("light.office", "turn_on", dry_run=False), self.identity, self.device)
        self.assertEqual(result.status, "failed")
        self.assertFalse(result.verified)
        assert result.error_code is not None
        self.assertTrue(result.error_code.startswith("home_assistant_unreachable"))

    # -- Milestone 0: Home Assistant brightness verification must compare the real 0-255
    #    attributes["brightness"] scale, not the outbound-only "brightness_pct" payload key --

    async def test_home_assistant_brightness_verified_true_within_tolerance(self) -> None:
        def fake_request(method: str, _url: str, _body: bytes | None, _headers: dict) -> tuple[int, bytes]:
            if method == "POST":
                return 200, b"{}"
            return 200, json.dumps({"state": "on", "attributes": {"brightness": 128}}).encode("utf-8")

        transport = HomeAssistantTransport(request=fake_request)
        result = await transport.execute(HomeAction("light.office", "set_brightness", {"brightness": 50}, dry_run=False))
        self.assertEqual(result.status, "succeeded")
        self.assertTrue(result.verified)

    async def test_home_assistant_brightness_verified_false_when_materially_wrong(self) -> None:
        def fake_request(method: str, _url: str, _body: bytes | None, _headers: dict) -> tuple[int, bytes]:
            if method == "POST":
                return 200, b"{}"
            return 200, json.dumps({"state": "on", "attributes": {"brightness": 10}}).encode("utf-8")

        transport = HomeAssistantTransport(request=fake_request)
        result = await transport.execute(HomeAction("light.office", "set_brightness", {"brightness": 50}, dry_run=False))
        self.assertEqual(result.status, "succeeded")
        self.assertFalse(result.verified)

    async def test_home_assistant_brightness_verified_false_when_attribute_missing(self) -> None:
        def fake_request(method: str, _url: str, _body: bytes | None, _headers: dict) -> tuple[int, bytes]:
            if method == "POST":
                return 200, b"{}"
            return 200, json.dumps({"state": "on", "attributes": {}}).encode("utf-8")

        transport = HomeAssistantTransport(request=fake_request)
        result = await transport.execute(HomeAction("light.office", "set_brightness", {"brightness": 50}, dry_run=False))
        self.assertEqual(result.status, "succeeded")
        self.assertFalse(result.verified)

    async def test_home_assistant_brightness_verified_false_when_attribute_non_numeric(self) -> None:
        def fake_request(method: str, _url: str, _body: bytes | None, _headers: dict) -> tuple[int, bytes]:
            if method == "POST":
                return 200, b"{}"
            return 200, json.dumps({"state": "on", "attributes": {"brightness": "bright"}}).encode("utf-8")

        transport = HomeAssistantTransport(request=fake_request)
        result = await transport.execute(HomeAction("light.office", "set_brightness", {"brightness": 50}, dry_run=False))
        self.assertEqual(result.status, "succeeded")
        self.assertFalse(result.verified)

    async def test_home_assistant_brightness_readback_failure_cannot_produce_verified_true(self) -> None:
        def fake_request(method: str, _url: str, _body: bytes | None, _headers: dict) -> tuple[int, bytes]:
            if method == "POST":
                return 200, b"{}"
            raise OSError("connection refused")

        transport = HomeAssistantTransport(request=fake_request)
        result = await transport.execute(HomeAction("light.office", "set_brightness", {"brightness": 50}, dry_run=False))
        self.assertEqual(result.status, "succeeded")
        self.assertFalse(result.verified)

    # -- F18A1-007: stale/missing computer-action approval must fail typed, never raise --

    async def test_computer_decide_returns_typed_failure_for_missing_pending_approval(self) -> None:
        result = await self.runtime.computer_actions.decide("approval-never-existed", True, self.identity.identity_id)
        self.assertEqual(result.status, "failed")
        self.assertFalse(result.verified)
        self.assertEqual(result.error_code, "pending_action_unavailable_after_restart")

    async def test_computer_decide_returns_typed_failure_on_repeated_decide_after_consumed(self) -> None:
        # clipboard_write is consequential but neither element- nor
        # window-targeted, so this approval-lifecycle test (F18A1-007) stays
        # decoupled from R18B02-003's window-target validation, which
        # `keyboard_action` now requires and which a fake "window-good" ref
        # cannot satisfy against the real WindowsDesktopProvider.
        pending = await self.runtime.computer_actions.execute(
            ComputerAction("clipboard_write", {"text": "hi"}),
            self.identity,
            self.device,
        )
        self.assertEqual(pending.status, "approval_required")
        assert pending.approval_id is not None
        first = await self.runtime.computer_actions.decide(pending.approval_id, False, self.identity.identity_id)
        self.assertEqual(first.status, "denied")
        second = await self.runtime.computer_actions.decide(pending.approval_id, True, self.identity.identity_id)
        self.assertEqual(second.status, "failed")
        self.assertFalse(second.verified)
        self.assertEqual(second.error_code, "pending_action_unavailable_after_restart")

    # -- F18A1-012: the real 2MB browser fetch cap must reject oversized bodies, not truncate/succeed silently --

    async def test_browser_fetch_enforces_two_megabyte_cap_on_the_real_production_path(self) -> None:
        class _PermissiveUrlPolicy:
            def validate(self, url: str, resolve_dns: bool = True) -> str:
                del resolve_dns
                return url

        class _OversizedResponse:
            def __init__(self, url: str) -> None:
                self._url = url

            def read(self, size: int) -> bytes:
                return b"x" * size

            def geturl(self) -> str:
                return self._url

            def __enter__(self) -> "_OversizedResponse":
                return self

            def __exit__(self, *_exc: object) -> bool:
                return False

        class _OversizedOpener:
            def open(self, request: object, timeout: float = 10) -> "_OversizedResponse":
                del timeout
                return _OversizedResponse(getattr(request, "full_url", "https://example.test/huge"))

        controller = LocalBrowserController(url_policy=_PermissiveUrlPolicy())
        with unittest.mock.patch("jarvis.browser.service.urllib.request.build_opener", return_value=_OversizedOpener()):
            with self.assertRaises(ValueError) as ctx:
                controller._fetch("https://example.test/huge")
        self.assertEqual(str(ctx.exception), "page_too_large")
