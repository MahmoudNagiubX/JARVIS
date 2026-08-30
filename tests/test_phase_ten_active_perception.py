from __future__ import annotations

import asyncio
import platform
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from jarvis.authority.identity.service import EnrollmentGrant
from jarvis.api.core import CoreApplication, DemoPrincipal
from jarvis.bootstrap import create_runtime
from jarvis.config import JarvisConfig
from jarvis.contracts import (
    ComputerAction,
    DesktopContextSnapshot,
    DesktopWindow,
    DeviceIdentity,
    LLMResponse,
    PerceptionPrivacyMode,
    ScreenObservation,
    ToolContext,
    ToolResultRetention,
    VisualRegion,
)
from jarvis.perception.cache import ObservationCache
from jarvis.perception.frame import TransientFrame, analyze_and_release
from jarvis.perception.privacy import PerceptionPrivacyPolicy
from jarvis.perception.providers import StaticPerceptionProvider
from jarvis.perception.windows import WindowsDesktopProvider, _WindowHandle
from jarvis.satellite_agent.agent import WindowsSatelliteAgent, SatelliteAgentConfig
from jarvis.devices.satellite.contracts import CommandObservation, SatelliteCommand, validate_command, validate_perception_output


SENTINEL = "VERY_SECRET_SCREEN_SENTINEL_123"


class _MetadataProvider(StaticPerceptionProvider):
    def __init__(self, process_name: str = "notepad.exe", title: str = "safe") -> None:
        super().__init__(SENTINEL)
        self.process_name = process_name
        self.title = title

    def desktop_context(self, device_id: str) -> DesktopContextSnapshot:
        window = DesktopWindow("window-test", self.title, self.process_name, 42, "Notepad", VisualRegion(0, 0, 800, 600), True, True)
        return DesktopContextSnapshot("snapshot-test", device_id, datetime.now(UTC), window, (window,), 1920, 1080, "test-provider", 1.0)


class _CountingProvider(_MetadataProvider):
    def __init__(self, *, process_name: str = "notepad.exe", title: str = "safe") -> None:
        super().__init__(process_name=process_name, title=title)
        self.context_calls = 0
        self.capture_calls = 0

    def desktop_context(self, device_id: str) -> DesktopContextSnapshot:
        self.context_calls += 1
        return super().desktop_context(device_id)

    async def capture(self, *args, **kwargs) -> ScreenObservation:
        self.capture_calls += 1
        return await super().capture(*args, **kwargs)


class _SharedWindowProvider(_MetadataProvider):
    def __init__(self) -> None:
        super().__init__(title="shared window")
        self.focused: str | None = None

    def desktop_context(self, device_id: str) -> DesktopContextSnapshot:
        window = DesktopWindow("window-shared", "shared window", "notepad.exe", 42, "Notepad", VisualRegion(0, 0, 800, 600), True, True)
        return DesktopContextSnapshot("snapshot-shared", device_id, datetime.now(UTC), window, (window,), 1920, 1080, "shared-test-provider", 1.0)

    def focus_window(self, window_ref: str) -> bool:
        self.focused = window_ref
        return window_ref == "window-shared"


class _WindowIdentityUser32:
    def __init__(self, process_id: int, window_class: str) -> None:
        self.process_id = process_id
        self.window_class = window_class

    def IsWindow(self, hwnd: int) -> bool:
        return hwnd == 100

    def IsWindowVisible(self, hwnd: int) -> bool:
        return hwnd == 100

    def GetWindowThreadProcessId(self, hwnd: int, process_id) -> int:
        del hwnd
        process_id._obj.value = self.process_id
        return 1

    def GetClassNameW(self, hwnd: int, buffer, size: int) -> int:
        del hwnd, size
        buffer.value = self.window_class
        return len(self.window_class)


class _Model:
    def __init__(self) -> None:
        self.requests = []
        self.calls = 0

    async def generate(self, request, route):
        del route
        self.requests.append(request)
        self.calls += 1
        if self.calls == 1:
            return LLMResponse("model-1", "", "test-model", "tool_calls", ({"function": {"name": "screen.observe", "arguments": {"mode": "screen"}}},), {})
        return LLMResponse("model-2", "The current visual observation was processed.", "test-model", "stop", (), {})


class PhaseTenActivePerceptionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:"))
        await self.runtime.start()
        self.identity = await self.runtime.identity.bootstrap_owner("Phase Ten Owner")
        grant = await self.runtime.identity.create_enrollment(
            EnrollmentGrant(self.identity.owner_id, "Perception Desktop", "desktop", "windows", ("tool.request",), ("computer.observe", "computer.input", "perception.screen"))
        )
        issued = await self.runtime.identity.redeem_enrollment(grant.code)
        self.device = await self.runtime.identity.authenticate(issued.raw, issued.device_id)
        assert self.device is not None

    async def asyncTearDown(self) -> None:
        await self.runtime.shutdown()

    def _use_provider(self, provider: object) -> None:
        self.runtime.perception.provider = provider
        if self.runtime.perception.router is not None:
            self.runtime.perception.router.local = provider

    async def _enroll_device(self, name: str, capabilities: tuple[str, ...]) -> DeviceIdentity:
        grant = await self.runtime.identity.create_enrollment(
            EnrollmentGrant(self.identity.owner_id, name, "desktop", "windows", ("tool.request",), capabilities)
        )
        issued = await self.runtime.identity.redeem_enrollment(grant.code)
        device = await self.runtime.identity.authenticate(issued.raw, issued.device_id)
        assert device is not None
        return device

    async def _connect_satellite(self, device: DeviceIdentity) -> tuple[CoreApplication, str]:
        application = CoreApplication(self.runtime)
        welcome = await application.satellite_connect(
            DemoPrincipal(self.identity, device),
            {
                "device_id": device.device_id,
                "owner_id": self.identity.owner_id,
                "platform": "windows",
                "capabilities": ["perception.screen"],
                "protocol_version": "2",
            },
        )
        self.assertTrue(welcome["accepted"])
        return application, str(welcome["session_id"])

    async def _complete_satellite_perception(
        self,
        device: DeviceIdentity,
        session_id: str,
        task: asyncio.Task,
        outputs: tuple[dict[str, object], ...],
    ) -> object:
        for output in outputs:
            command = await self.runtime.satellite_transport.poll(
                self.identity.owner_id, device.device_id, session_id, wait_seconds=1
            )
            self.assertIsNotNone(command)
            assert command is not None
            self.assertEqual(command.action, "perception")
            submission = await self.runtime.satellite_transport.submit_result(
                self.identity.owner_id,
                device.device_id,
                session_id,
                CommandObservation(command.command_id, "completed", output),
            )
            self.assertTrue(submission.accepted)
        return await asyncio.wait_for(task, timeout=2)

    async def test_native_windows_context_is_bounded_and_refs_are_ephemeral(self) -> None:
        provider = WindowsDesktopProvider()
        context = provider.desktop_context(self.device.device_id)
        if platform.system().casefold() == "windows":
            self.assertLessEqual(len(context.windows), 50)
            self.assertGreater(context.display_width or 0, 0)
            self.assertGreater(context.display_height or 0, 0)
            if context.active_window:
                self.assertTrue(context.active_window.window_ref.startswith("window-"))
                self.assertIsNone(getattr(context.active_window, "hwnd", None))
        else:
            self.assertEqual(provider.reason, "windows_desktop_unavailable")

    async def test_context_snapshot_contract_bounds_windows_and_strings(self) -> None:
        with self.assertRaisesRegex(ValueError, "50"):
            DesktopContextSnapshot("s", "d", datetime.now(UTC), windows=tuple(DesktopWindow(f"window-{i}") for i in range(51)))
        with self.assertRaisesRegex(ValueError, "title"):
            DesktopContextSnapshot("s", "d", datetime.now(UTC), windows=(DesktopWindow("window-1", "x" * 301),))
        with self.assertRaisesRegex(ValueError, "process"):
            DesktopContextSnapshot("s", "d", datetime.now(UTC), windows=(DesktopWindow("window-1", process_name="x" * 201),))

    async def test_invalid_negative_and_oversized_regions_fail_before_capture(self) -> None:
        self._use_provider(_MetadataProvider())
        for region, code in ((VisualRegion(-1, 0, 1, 1), "invalid_capture_region"), (VisualRegion(0, 0, 0, 1), "invalid_capture_region"), (VisualRegion(0, 0, 12_001, 1_001), "capture_region_too_large")):
            result = await self.runtime.perception.observe_screen(self.identity, self.device, region=region, mode="screen")
            self.assertEqual(result.error_code, code)

    async def test_privacy_modes_metadata_only_and_off_fail_closed_for_pixels(self) -> None:
        self._use_provider(_MetadataProvider())
        self.runtime.perception.privacy.set_mode(PerceptionPrivacyMode.METADATA_ONLY)
        metadata = await self.runtime.perception.observe_desktop_context(self.identity, self.device)
        self.assertEqual(metadata.status, "completed")
        pixels = await self.runtime.perception.observe_screen(self.identity, self.device, mode="screen")
        self.assertEqual(pixels.error_code, "privacy_policy_denied")
        self.runtime.perception.privacy.set_mode("off")
        self.assertEqual((await self.runtime.perception.observe_desktop_context(self.identity, self.device)).error_code, "privacy_policy_denied")

    async def test_sensitive_window_policy_does_not_publish_title(self) -> None:
        provider = _MetadataProvider(process_name="credential-manager.exe", title="Private password vault")
        self._use_provider(provider)
        self.runtime.perception.privacy = PerceptionPrivacyPolicy(denied_processes=frozenset({"credential-manager.exe"}))
        result = await self.runtime.perception.observe_desktop_context(self.identity, self.device)
        self.assertEqual(result.error_code, "privacy_policy_denied")
        serialized = str(self.runtime.repository.events()) + str(self.runtime.repository.audit())
        self.assertNotIn("Private password vault", serialized)

    async def test_owner_device_session_cache_isolation_and_ttl(self) -> None:
        cache = ObservationCache(ttl_seconds=1, max_per_owner=2, max_total=3)
        now = datetime(2026, 1, 1, tzinfo=UTC)
        value = ScreenObservation("observation-1", "device-a", now, "test")
        cache.put("owner-a", "device-a", "session-a", value, now=now)
        self.assertIs(cache.get("owner-a", "device-a", "session-a", "observation-1", now=now), value)
        self.assertIsNone(cache.get("owner-b", "device-a", "session-a", "observation-1", now=now))
        self.assertIsNone(cache.get("owner-a", "device-b", "session-a", "observation-1", now=now))
        self.assertIsNone(cache.get("owner-a", "device-a", "session-b", "observation-1", now=now))
        self.assertIsNone(cache.get("owner-a", "device-a", "session-a", "observation-1", now=now + timedelta(seconds=2)))

    async def test_latest_rechecks_owner_capability_and_device_status(self) -> None:
        self._use_provider(_MetadataProvider())
        captured = await self.runtime.perception.observe_screen(self.identity, self.device, mode="semantic")
        self.assertEqual(captured.status, "completed")
        latest = await self.runtime.perception.latest_observation(self.identity, self.device)
        self.assertEqual(latest.status, "completed")
        wrong_owner = replace(self.device, owner_id="owner-other")
        self.assertEqual((await self.runtime.perception.latest_observation(self.identity, wrong_owner)).error_code, "target_owner_mismatch")
        await self.runtime.device_fabric.revoke(self.identity.owner_id, self.device.device_id)
        self.assertEqual((await self.runtime.perception.latest_observation(self.identity, self.device)).error_code, "perception_target_revoked")

    async def test_explicit_offline_target_never_falls_back_to_local_provider(self) -> None:
        class CountingProvider(_MetadataProvider):
            def __init__(self):
                super().__init__()
                self.context_calls = 0

            def desktop_context(self, device_id: str) -> DesktopContextSnapshot:
                self.context_calls += 1
                return super().desktop_context(device_id)

        provider = CountingProvider()
        self._use_provider(provider)
        grant = await self.runtime.identity.create_enrollment(
            EnrollmentGrant(self.identity.owner_id, "Offline Target", "desktop", "windows", ("tool.request",), ("perception.screen",))
        )
        issued = await self.runtime.identity.redeem_enrollment(grant.code)
        target = await self.runtime.identity.authenticate(issued.raw, issued.device_id)
        assert target is not None
        await self.runtime.device_fabric.mark_offline(self.identity.owner_id, target.device_id)
        result = await self.runtime.perception.observe_desktop_context(self.identity, self.device, target_device=target)
        self.assertEqual(result.error_code, "perception_target_offline")
        self.assertEqual(provider.context_calls, 0)

    async def test_metadata_awareness_scheduler_is_explicit_opt_in(self) -> None:
        runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:", desktop_awareness_enabled=True))
        try:
            self.assertEqual([job.name for job in runtime.scheduler.jobs.values()].count("desktop-metadata-awareness"), 1)
        finally:
            await runtime.start()
            await runtime.shutdown()

    async def test_cache_is_bounded_and_shutdown_clears_it(self) -> None:
        self._use_provider(_MetadataProvider())
        for _ in range(10):
            await self.runtime.perception.observe_screen(self.identity, self.device, mode="screen")
        self.assertLessEqual(len(self.runtime.perception.cache), 8)
        await self.runtime.perception.shutdown()
        self.assertEqual(len(self.runtime.perception.cache), 0)

    async def test_transient_frame_released_on_success_and_analyzer_error(self) -> None:
        frame = TransientFrame(2, 2, "BGRA32", datetime.now(UTC), VisualRegion(0, 0, 2, 2), bytearray(b"secret-frame"))
        self.assertEqual(await analyze_and_release(frame, lambda item: len(item.data)), len(b"secret-frame"))
        self.assertTrue(frame.released)
        self.assertEqual(bytes(frame.data), b"")
        failed = TransientFrame(2, 2, "BGRA32", datetime.now(UTC), VisualRegion(0, 0, 2, 2), bytearray(b"secret-frame"))
        async def explode(_):
            raise RuntimeError("analyzer_failed")
        with self.assertRaisesRegex(RuntimeError, "analyzer_failed"):
            await analyze_and_release(failed, explode)
        self.assertTrue(failed.released)

    async def test_same_owner_target_accepted_and_wrong_owner_or_capability_denied(self) -> None:
        self._use_provider(_MetadataProvider())
        accepted = await self.runtime.perception.observe_desktop_context(self.identity, self.device, target_device=self.device)
        self.assertEqual(accepted.status, "completed")
        wrong_owner = replace(self.device, owner_id="owner-other")
        self.assertEqual((await self.runtime.perception.observe_desktop_context(self.identity, wrong_owner)).error_code, "target_owner_mismatch")
        missing = replace(self.device, capabilities=frozenset({"computer.observe"}))
        self.assertEqual((await self.runtime.perception.observe_desktop_context(self.identity, missing)).error_code, "target_capability_missing")

    async def test_revoked_and_offline_targets_fail_without_local_fallback(self) -> None:
        self._use_provider(_MetadataProvider())
        await self.runtime.device_fabric.mark_offline(self.identity.owner_id, self.device.device_id)
        offline = await self.runtime.perception.observe_desktop_context(self.identity, self.device)
        self.assertEqual(offline.error_code, "perception_target_offline")
        # Revoke has its own fail-closed reason and cannot fall back to local capture.
        await self.runtime.device_fabric.revoke(self.identity.owner_id, self.device.device_id)
        revoked = await self.runtime.perception.observe_desktop_context(self.identity, self.device)
        self.assertEqual(revoked.error_code, "perception_target_revoked")

    async def test_active_context_projects_safe_metadata_and_coalesces_identical_samples(self) -> None:
        self._use_provider(_MetadataProvider())
        first = await self.runtime.perception.observe_desktop_context(self.identity, self.device)
        before = len([item for item in self.runtime.repository.events() if item["event_type"] == "world_state.observation"])
        second = await self.runtime.perception.observe_desktop_context(self.identity, self.device)
        after = len([item for item in self.runtime.repository.events() if item["event_type"] == "world_state.observation"])
        self.assertEqual(first.status, second.status, "identical samples remain usable")
        self.assertEqual(before, after)
        facts = str([dict(row) for row in self.runtime.repository.database.connection.execute("SELECT key, value_json FROM world_facts").fetchall()])
        self.assertIn("desktop.", facts)
        self.assertNotIn("safe", facts)

    async def test_visual_tools_are_in_existing_registry_and_are_ephemeral(self) -> None:
        specs = {item.name: item for item in self.runtime.tools.list()}
        self.assertTrue({"desktop.context.read", "screen.observe", "screen.latest"}.issubset(specs))
        self.assertEqual(specs["screen.observe"].retention, ToolResultRetention.EPHEMERAL)
        self.assertEqual(specs["screen.latest"].retention, ToolResultRetention.EPHEMERAL)
        self._use_provider(_MetadataProvider())
        result = await self.runtime.tool_service.execute("screen.observe", {"mode": "screen"}, __import__("jarvis.contracts", fromlist=["ToolContext"]).ToolContext(self.identity, self.device, "phase10", "phase10"))
        self.assertEqual(result.status.value, "completed")
        self.assertEqual(result.retention, ToolResultRetention.EPHEMERAL)

    async def test_agent_receives_visual_text_current_turn_but_does_not_persist_it(self) -> None:
        provider = _MetadataProvider()
        self._use_provider(provider)
        model = _Model()
        self.runtime.agent.models = model
        outcome = await self.runtime.agent.process_text("what is on my screen", self.identity, self.device)
        self.assertEqual(outcome.state.value, "succeeded")
        request_text = str(model.requests)
        self.assertIn(SENTINEL, request_text)
        run = self.runtime.repository.run(outcome.run_id)
        assert run is not None
        self.assertNotIn(SENTINEL, str(run.context))
        durable = " ".join((str(self.runtime.repository.events()), str(self.runtime.repository.audit()), str(self.runtime.repository.database.connection.execute("SELECT * FROM tool_calls").fetchall()), str(self.runtime.repository.database.connection.execute("SELECT * FROM messages").fetchall()), str(self.runtime.repository.database.connection.execute("SELECT * FROM memories").fetchall()), str(self.runtime.repository.database.connection.execute("SELECT * FROM world_facts").fetchall())))
        self.assertNotIn(SENTINEL, durable)

    async def test_unrelated_prompt_does_not_auto_capture(self) -> None:
        class CountingProvider(_MetadataProvider):
            def __init__(self):
                super().__init__()
                self.calls = 0
            async def capture(self, *args, **kwargs):
                self.calls += 1
                return await super().capture(*args, **kwargs)
        provider = CountingProvider()
        self._use_provider(provider)
        class DirectModel:
            async def generate(self, request, route):
                del request, route
                return LLMResponse("direct", "No visual context was requested.", "test-model", "stop", (), {})
        self.runtime.agent.models = DirectModel()
        await self.runtime.agent.process_text("tell me a short joke", self.identity, self.device)
        self.assertEqual(provider.calls, 0)

    async def test_satellite_v2_and_raw_result_rejection(self) -> None:
        command = SatelliteCommand("perception-1", "perception", "perception.screen", {"operation": "observe_screen"}, True, "2")
        validate_command(command)
        with self.assertRaisesRegex(ValueError, "raw_perception"):
            validate_perception_output({"screenshot": "bytes"})
        with self.assertRaisesRegex(ValueError, "raw_perception"):
            validate_perception_output({"value": "data:image/png;base64,AAAA"})
        self.assertEqual(SatelliteCommand("computer-1", "observe", "computer.observe").protocol_version, "1")

    async def test_satellite_perception_rejects_raw_or_malformed_request_parameters(self) -> None:
        from jarvis.satellite_agent.agent import SatelliteAgentConfig, WindowsSatelliteAgent

        agent = WindowsSatelliteAgent(
            SatelliteAgentConfig("http://127.0.0.1:8000", self.identity.owner_id, self.identity.identity_id, self.device.device_id, frozenset({"perception.screen"}), protocol_version="2"),
            "credential",
            perception_provider=_MetadataProvider(),
        )
        raw = await agent.execute_command(SatelliteCommand("perception-raw", "perception", "perception.screen", {"operation": "observe_screen", "screenshot": "bytes"}, True, "2"))
        malformed = await agent.execute_command(SatelliteCommand("perception-region", "perception", "perception.screen", {"operation": "observe_screen", "region": "not-an-object"}, True, "2"))
        self.assertEqual(raw.error_code, "invalid_perception_parameters")
        self.assertEqual(malformed.error_code, "invalid_perception_region")

    async def test_v2_satellite_context_round_trip_uses_structured_result(self) -> None:
        application = CoreApplication(self.runtime)
        welcome = await application.satellite_connect(
            DemoPrincipal(self.identity, self.device),
            {"device_id": self.device.device_id, "owner_id": self.identity.owner_id, "platform": "windows", "capabilities": ["perception.screen"], "protocol_version": "2"},
        )
        self.assertTrue(welcome["accepted"])
        session_id = str(welcome["session_id"])
        task = asyncio.create_task(self.runtime.perception.observe_desktop_context(self.identity, self.device, session_id="satellite-session"))
        command = await self.runtime.satellite_transport.poll(self.identity.owner_id, self.device.device_id, session_id, wait_seconds=1)
        self.assertIsNotNone(command)
        assert command is not None
        self.assertEqual(command.action, "perception")
        self.assertEqual(command.protocol_version, "2")
        self.assertEqual(command.parameters["operation"], "observe_desktop_context")
        await self.runtime.satellite_transport.submit_result(
            self.identity.owner_id,
            self.device.device_id,
            session_id,
            __import__("jarvis.devices.satellite.contracts", fromlist=["CommandObservation"]).CommandObservation(
                command.command_id, "completed", {"snapshot_id": "snapshot-remote", "device_id": self.device.device_id, "observed_at": datetime.now(UTC).isoformat(), "windows": [], "source": "satellite", "confidence": 1.0},
            ),
        )
        result = await asyncio.wait_for(task, timeout=2)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.context.source, "satellite")

    async def test_raw_hwnd_is_not_a_focus_reference(self) -> None:
        provider = WindowsDesktopProvider()
        with self.assertRaisesRegex(ValueError, "window_ref"):
            provider.resolve_window_ref("123456")

    async def test_malformed_target_and_window_references_fail_closed(self) -> None:
        self._use_provider(_MetadataProvider())
        target = await self.runtime.perception.resolve_target(self.identity, self.device, 123)
        self.assertIsNone(target)
        malformed = await self.runtime.perception.observe_screen(self.identity, self.device, window_ref=123, mode="semantic")
        self.assertEqual(malformed.error_code, "window_ref_required")

    async def test_focus_window_revalidates_ephemeral_reference(self) -> None:
        context = await self.runtime.perception.observe_desktop_context(self.identity, self.device)
        if context.context is None or context.context.active_window is None:
            self.skipTest("no active Windows window")
        window_ref = context.context.active_window.window_ref
        provider = self.runtime.perception.provider
        provider._window_refs[window_ref].expires_at = datetime.now(UTC) - timedelta(seconds=1)
        result = await self.runtime.computer_actions.execute(ComputerAction("focus_window", {"window_ref": window_ref}, False), self.identity, self.device)
        self.assertEqual(result.error_code, "window_ref_expired")

    async def test_same_id_online_routes_context_and_screen_to_satellite(self) -> None:
        provider = _CountingProvider()
        self._use_provider(provider)
        application, session_id = await self._connect_satellite(self.device)
        try:
            context_task = asyncio.create_task(
                self.runtime.perception.observe_desktop_context(self.identity, self.device, session_id="same-id-online")
            )
            context_result = await self._complete_satellite_perception(
                self.device,
                session_id,
                context_task,
                ({
                    "snapshot_id": "snapshot-same-id",
                    "device_id": self.device.device_id,
                    "observed_at": datetime.now(UTC).isoformat(),
                    "windows": [],
                    "source": "satellite",
                    "confidence": 1.0,
                },),
            )
            self.assertEqual(context_result.status, "completed")
            self.assertEqual(context_result.context.source, "satellite")

            screen_task = asyncio.create_task(
                self.runtime.perception.observe_screen(self.identity, self.device, mode="screen", session_id="same-id-online")
            )
            screen_result = await self._complete_satellite_perception(
                self.device,
                session_id,
                screen_task,
                (
                    {
                        "snapshot_id": "snapshot-same-id-screen",
                        "device_id": self.device.device_id,
                        "observed_at": datetime.now(UTC).isoformat(),
                        "windows": [],
                        "source": "satellite",
                        "confidence": 1.0,
                    },
                    {
                        "observation_id": "observation-same-id",
                        "device_id": self.device.device_id,
                        "captured_at": datetime.now(UTC).isoformat(),
                        "source": "satellite",
                        "width": 1920,
                        "height": 1080,
                        "raw_retained": False,
                        "confidence": 1.0,
                        "metadata": {},
                    },
                ),
            )
            self.assertEqual(screen_result.status, "completed")
            self.assertEqual(screen_result.observation.source, "satellite")
            self.assertEqual(provider.context_calls, 0)
            self.assertEqual(provider.capture_calls, 0)
        finally:
            await application.satellite_disconnect(DemoPrincipal(self.identity, self.device), session_id)

    async def test_same_id_offline_routes_context_and_screen_fail_closed_without_local_fallback(self) -> None:
        provider = _CountingProvider()
        self._use_provider(provider)
        application, session_id = await self._connect_satellite(self.device)
        await application.satellite_disconnect(DemoPrincipal(self.identity, self.device), session_id)

        context = await self.runtime.perception.observe_desktop_context(self.identity, self.device)
        screen = await self.runtime.perception.observe_screen(self.identity, self.device, mode="screen")
        self.assertEqual(context.error_code, "perception_target_offline")
        self.assertEqual(screen.error_code, "perception_target_offline")
        self.assertEqual(provider.context_calls, 0)
        self.assertEqual(provider.capture_calls, 0)

    async def test_genuine_local_target_still_uses_local_provider(self) -> None:
        provider = _CountingProvider()
        self._use_provider(provider)
        context = await self.runtime.perception.observe_desktop_context(self.identity, self.device)
        semantic = await self.runtime.perception.observe_screen(self.identity, self.device, mode="semantic")
        self.assertEqual(context.status, "completed")
        self.assertEqual(semantic.status, "completed")
        self.assertGreater(provider.context_calls, 0)
        self.assertEqual(provider.capture_calls, 0)

    async def test_desktop_context_tool_is_ephemeral_and_title_sentinel_never_persists(self) -> None:
        sentinel = "PRIVATE_WINDOW_TITLE_SENTINEL_7842"
        self._use_provider(_MetadataProvider(title=sentinel))

        class ContextModel:
            def __init__(self) -> None:
                self.requests = []
                self.calls = 0

            async def generate(self, request, route):
                del route
                self.requests.append(request)
                self.calls += 1
                if self.calls == 1:
                    return LLMResponse(
                        "context-tool-request",
                        "",
                        "test-model",
                        "tool_calls",
                        ({"function": {"name": "desktop.context.read", "arguments": {}}},),
                        {},
                    )
                return LLMResponse("context-answer", "Desktop metadata was processed for this turn.", "test-model", "stop", (), {})

        model = ContextModel()
        self.runtime.agent.models = model
        outcome = await self.runtime.agent.process_text("describe my current desktop", self.identity, self.device)
        self.assertEqual(outcome.state.value, "succeeded")
        self.assertIn(sentinel, str(model.requests))
        self.assertNotIn(sentinel, outcome.response or "")

        specs = {item.name: item for item in self.runtime.tools.list()}
        self.assertEqual(specs["desktop.context.read"].retention, ToolResultRetention.EPHEMERAL)
        run = self.runtime.repository.run(outcome.run_id)
        assert run is not None
        durable_values = [
            str(run.context),
            str(self.runtime.repository.messages(run.conversation_id)),
            str(self.runtime.repository.events()),
            str(self.runtime.repository.audit()),
            str(self.runtime.repository.database.connection.execute("SELECT * FROM tool_calls").fetchall()),
            str(self.runtime.repository.database.connection.execute("SELECT * FROM messages").fetchall()),
            str(self.runtime.repository.database.connection.execute("SELECT * FROM memories").fetchall()),
            str(self.runtime.repository.database.connection.execute("SELECT * FROM world_facts").fetchall()),
            str(await CoreApplication(self.runtime).experience_state(self.identity.owner_id)),
            CoreApplication(self.runtime).experience_hud(),
        ]
        self.assertTrue(all(sentinel not in value for value in durable_values))

    async def test_remote_observe_to_focus_uses_one_shared_satellite_provider(self) -> None:
        provider = _SharedWindowProvider()
        agent = WindowsSatelliteAgent(
            SatelliteAgentConfig(
                "http://127.0.0.1:8000",
                self.identity.owner_id,
                self.identity.identity_id,
                self.device.device_id,
                frozenset({"perception.screen", "computer.input"}),
                protocol_version="2",
            ),
            "credential",
            perception_provider=provider,
        )
        context = await agent.execute_command(
            SatelliteCommand(
                "perception-shared",
                "perception",
                "perception.screen",
                {"operation": "observe_desktop_context"},
                True,
                "2",
            )
        )
        self.assertEqual(context.status, "completed")
        self.assertEqual(context.output["active_window"]["window_ref"], "window-shared")
        with patch("jarvis.computer.service.platform.system", return_value="Windows"):
            focus = await agent.execute_command(
                SatelliteCommand(
                    "focus-shared",
                    "input",
                    "computer.input",
                    {"operation": "focus_window", "window_ref": "window-shared"},
                    False,
                )
            )
        self.assertEqual(focus.status, "completed")
        self.assertEqual(provider.focused, "window-shared")
        self.assertIs(agent._controller.perception_provider, provider)

    async def test_legacy_window_capture_uses_canonical_privacy_and_capability_authority(self) -> None:
        provider = _CountingProvider()
        self._use_provider(provider)
        accepted = await CoreApplication(self.runtime).perception_window(self.identity, self.device, "window-test")
        self.assertEqual(accepted["status"], "completed")
        self.assertEqual(provider.capture_calls, 1)

        missing_capability = replace(self.device, capabilities=frozenset({"computer.observe"}))
        denied = await self.runtime.perception.capture_window(self.identity, missing_capability, "window-test")
        self.assertEqual(denied.error_code, "target_capability_missing")
        self.assertEqual(provider.capture_calls, 1)

        sensitive = _CountingProvider(process_name="credential-manager.exe", title="Private password vault")
        self._use_provider(sensitive)
        self.runtime.perception.privacy = PerceptionPrivacyPolicy(denied_processes=frozenset({"credential-manager.exe"}))
        privacy_denied = await CoreApplication(self.runtime).perception_window(self.identity, self.device, "window-test")
        self.assertEqual(privacy_denied["error_code"], "privacy_policy_denied")
        self.assertEqual(sensitive.capture_calls, 0)

    async def test_screen_latest_resolves_remote_target_and_rejects_wrong_target_or_owner(self) -> None:
        target = await self._enroll_device("Remote Perception", ("perception.screen",))
        application, session_id = await self._connect_satellite(target)
        try:
            observation_task = asyncio.create_task(
                self.runtime.perception.observe_screen(
                    self.identity,
                    self.device,
                    target_device=target,
                    mode="screen",
                    session_id="remote-latest",
                )
            )
            observed = await self._complete_satellite_perception(
                target,
                session_id,
                observation_task,
                (
                    {
                        "snapshot_id": "snapshot-remote-latest",
                        "device_id": target.device_id,
                        "observed_at": datetime.now(UTC).isoformat(),
                        "windows": [],
                        "source": "satellite",
                        "confidence": 1.0,
                    },
                    {
                        "observation_id": "observation-remote-latest",
                        "device_id": target.device_id,
                        "captured_at": datetime.now(UTC).isoformat(),
                        "source": "satellite",
                        "width": 1280,
                        "height": 720,
                        "raw_retained": False,
                        "confidence": 1.0,
                        "metadata": {},
                    },
                ),
            )
            self.assertEqual(observed.status, "completed")
            observation_id = observed.observation.observation_id
            tool_context = ToolContext(self.identity, self.device, "remote-latest", "remote-latest")
            latest = await self.runtime.tool_service.execute(
                "screen.latest",
                {"target_device_id": target.device_id, "observation_id": observation_id},
                tool_context,
            )
            self.assertEqual(latest.status.value, "completed")
            self.assertEqual(latest.output["observation"]["device_id"], target.device_id)

            wrong_target = await self.runtime.tool_service.execute(
                "screen.latest", {"observation_id": observation_id}, tool_context
            )
            self.assertEqual(wrong_target.status.value, "failed")
            self.assertEqual(wrong_target.error_code, "observation_not_found_or_expired")

            wrong_owner = replace(target, owner_id="owner-not-the-requester")
            cross_owner = await self.runtime.perception.latest_observation(
                self.identity,
                self.device,
                target_device=wrong_owner,
                observation_id=observation_id,
                session_id="remote-latest",
            )
            self.assertEqual(cross_owner.error_code, "target_owner_mismatch")
        finally:
            await application.satellite_disconnect(DemoPrincipal(self.identity, target), session_id)

    async def test_window_ref_rejects_hwnd_reuse_by_pid_or_class_change(self) -> None:
        provider = WindowsDesktopProvider.__new__(WindowsDesktopProvider)
        provider._window_refs = {
            "window-reused": _WindowHandle(
                100,
                10,
                "title-digest",
                "Notepad",
                datetime.now(UTC) + timedelta(seconds=30),
            )
        }
        provider._user32 = _WindowIdentityUser32(99, "Notepad")
        with self.assertRaisesRegex(ValueError, "window_ref_expired"):
            provider.resolve_window_ref("window-reused")
        self.assertNotIn("window-reused", provider._window_refs)

        provider._window_refs = {
            "window-changed": _WindowHandle(
                100,
                10,
                "title-digest",
                "Notepad",
                datetime.now(UTC) + timedelta(seconds=30),
            )
        }
        provider._user32 = _WindowIdentityUser32(10, "Calculator")
        with self.assertRaisesRegex(ValueError, "window_ref_changed"):
            provider.resolve_window_ref("window-changed")
        self.assertNotIn("window-changed", provider._window_refs)


if __name__ == "__main__":
    unittest.main()
