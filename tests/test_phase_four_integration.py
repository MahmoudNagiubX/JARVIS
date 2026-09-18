from __future__ import annotations

import json
import threading
import unittest
from datetime import UTC, datetime, timedelta
from urllib.request import Request, urlopen

from jarvis.api.core import CoreApplication, DemoPrincipal
from jarvis.api.http import CoreHttpServer
from jarvis.authority.identity.service import EnrollmentGrant
from jarvis.bootstrap import create_runtime
from jarvis.browser.service import BrowserActionService, LocalBrowserController, PlaywrightBrowserController
from jarvis.capabilities.registry import CapabilityRegistry
from jarvis.config import JarvisConfig
from jarvis.contracts import (
    BrowserAction,
    CapabilityDescriptor,
    CommunicationMessage,
    ComputerAction,
    DeviceHeartbeat,
    DeviceIdentity,
    DeviceRecord,
    DeviceRole,
    DeviceStatus,
    HomeAction,
    HomeEntity,
    Identity,
    Notification,
    ToolContext,
    VoiceEndpoint,
)
from jarvis.devices.home.service import HomeActionService, InMemoryHomeTransport, RestrictedMQTTTransport


class PhaseFourIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:"))
        await self.runtime.start()
        self.identity = await self.runtime.identity.bootstrap_owner("Phase Four Owner")
        enrollment = await self.runtime.identity.create_enrollment(
            EnrollmentGrant(
                self.identity.owner_id,
                "Phase Four Device",
                "desktop",
                "windows",
                ("tool.request",),
                (
                    "computer.observe", "computer.input", "browser.open_url", "browser.read_page",
                    "browser.inspect_accessibility_tree", "browser.tabs", "browser.click", "home.read", "home.control",
                    "communication.send",
                ),
            )
        )
        issued = await self.runtime.identity.redeem_enrollment(enrollment.code)
        self.credential = issued.raw
        self.device = await self.runtime.identity.authenticate(issued.raw, issued.device_id)
        assert self.device is not None

    async def asyncTearDown(self) -> None:
        await self.runtime.shutdown()

    async def test_computer_boundary_is_typed_bounded_and_approval_aware(self) -> None:
        observed = await self.runtime.computer_actions.execute(
            ComputerAction("list_processes", dry_run=True), self.identity, self.device
        )
        self.assertEqual(observed.status, "succeeded")
        self.assertTrue(observed.verified)

        # clipboard_write is consequential but neither element- nor
        # window-targeted, so this generic approval-gate test stays
        # decoupled from R18B02-003's window-target validation (which
        # keyboard_action now requires and this synthetic {"keys": [...]}
        # shape - predating the current handler's real parameter contract -
        # was never meant to satisfy).
        pending = await self.runtime.computer_actions.execute(
            ComputerAction("clipboard_write", {"text": "ctrl-l-equivalent"}, dry_run=True), self.identity, self.device
        )
        self.assertEqual(pending.status, "approval_required")
        self.assertIsNotNone(pending.approval_id)
        completed = await self.runtime.computer_actions.decide(pending.approval_id or "", True, self.identity.identity_id)
        self.assertEqual(completed.status, "succeeded")

    async def test_local_browser_reads_deterministic_page_and_rejects_unsupported_interaction(self) -> None:
        def fetcher(url: str) -> tuple[str, str]:
            return "<html><h1>Local Page</h1><a href='https://example.test/next'>Next</a><p>Hello JARVIS</p></html>", url

        service = BrowserActionService(
            LocalBrowserController(fetcher), self.runtime.repository, self.runtime.event_bus,
            self.runtime.permission, self.runtime.audit, self.runtime.approval,
        )
        opened = await service.execute(BrowserAction("open_url", {"url": "https://example.test"}), self.identity, self.device)
        self.assertEqual(opened.status, "succeeded")
        session_id = str(opened.output["session_id"])
        page = await service.execute(BrowserAction("read_page", {"session_id": session_id}), self.identity, self.device)
        self.assertEqual(page.status, "succeeded")
        self.assertIn("Hello JARVIS", str(page.output["text"]))
        click = await service.execute(BrowserAction("click", {"session_id": session_id, "selector": "a"}), self.identity, self.device)
        self.assertEqual(click.status, "approval_required")
        playwright = await PlaywrightBrowserController().execute(
            BrowserAction("read_page", {"session_id": session_id}), ToolContext(self.identity, self.device, "browser", "browser-test")
        )
        self.assertEqual(playwright.error_code, "playwright_adapter_not_available")

    async def test_device_fabric_registers_heartbeats_stale_state_and_revocation(self) -> None:
        device = DeviceRecord(
            "satellite-1", self.identity.owner_id, "Office Satellite", DeviceRole.ROOM_SATELLITE.value,
            "loopback", DeviceStatus.REGISTERED.value, frozenset({"voice.input", "voice.output"}),
            "trusted", datetime.now(UTC) - timedelta(minutes=5), "office", {"platform": "windows"},
        )
        registered = await self.runtime.device_fabric.register(device)
        self.assertEqual(registered.status, DeviceStatus.ONLINE.value)
        stale = await self.runtime.device_fabric.mark_stale_offline(self.identity.owner_id, 60)
        self.assertEqual([item.device_id for item in stale], ["satellite-1"])
        self.assertEqual(await self.runtime.device_fabric.capabilities(self.identity.owner_id, "satellite-1"), ())
        online = await self.runtime.device_fabric.heartbeat(DeviceHeartbeat("satellite-1", datetime.now(UTC)), self.identity.owner_id)
        self.assertEqual(online.status, DeviceStatus.ONLINE.value)
        revoked = await self.runtime.device_fabric.revoke(self.identity.owner_id, "satellite-1")
        self.assertEqual(revoked.status, DeviceStatus.REVOKED.value)

    async def test_home_actions_are_allowlisted_and_mqtt_topics_restricted(self) -> None:
        entity = HomeEntity("light.office", "Office light", "light", "off", {"brightness": 0}, "office")
        mqtt = RestrictedMQTTTransport(publisher=lambda topic, payload: True)
        home = HomeActionService(
            InMemoryHomeTransport((entity,)), self.runtime.repository, self.runtime.event_bus,
            self.runtime.permission, self.runtime.audit, mqtt,
        )
        self.assertEqual(len(await home.list_entities(self.identity, self.device)), 1)
        turned_on = await home.execute(HomeAction("light.office", "turn_on", dry_run=False), self.identity, self.device)
        self.assertEqual(turned_on.status, "succeeded")
        state = await home.execute(HomeAction("light.office", "read_state", dry_run=False), self.identity, self.device)
        self.assertEqual(state.output["state"], "on")
        blocked = await home.execute(HomeAction("lock.front_door", "lock", dry_run=False), self.identity, self.device)
        self.assertEqual(blocked.error_code, "home_action_blocked")
        self.assertTrue(await mqtt.publish("jarvis/office/light", "on"))
        self.assertFalse(await mqtt.publish("admin/override", "on"))

    async def test_communications_notifications_voice_and_capabilities(self) -> None:
        draft = await self.runtime.communications.draft(self.identity.owner_id, "local", "owner", "Draft this")
        self.assertEqual(draft.channel, "local")
        pending = await self.runtime.communications.send(self.identity.owner_id, "local", "owner", "Send this", self.identity, self.device)
        self.assertEqual(pending.status, "approval_required")
        sent = await self.runtime.communications.decide_send(self.identity.owner_id, pending.approval_id or "", True, self.identity.identity_id)
        self.assertEqual(sent.status, "sent")
        messages = await self.runtime.communications.list_messages(self.identity.owner_id)
        self.assertEqual(len(messages), 1)

        first = await self.runtime.notifications.create(self.identity.owner_id, "Build", "Build finished", dedup_key="build-1")
        duplicate = await self.runtime.notifications.create(self.identity.owner_id, "Build", "Build finished", dedup_key="build-1")
        self.assertEqual(first.notification_id, duplicate.notification_id)
        dismissed = await self.runtime.notifications.dismiss(self.identity.owner_id, first.notification_id)
        self.assertIsNotNone(dismissed.dismissed_at)

        source = await self.runtime.voice_routing.register(self.identity.owner_id, VoiceEndpoint("mic-office", "satellite-1", "office", True, False))
        await self.runtime.voice_routing.register(self.identity.owner_id, VoiceEndpoint("speaker-office", "speaker-1", "office", False, True))
        route = await self.runtime.voice_routing.select(self.identity.owner_id, "voice-session", source.endpoint_id)
        self.assertEqual(route.output_endpoint_id, "speaker-office")

        registry = CapabilityRegistry()
        registry.register(CapabilityDescriptor("test.local", "test", None, True, "read"))
        registry.register(CapabilityDescriptor("test.offline", "test", None, False, "read"))
        self.assertEqual([item.capability_id for item in registry.list()], ["test.local"])

    async def test_phase_four_loopback_endpoints(self) -> None:
        application = CoreApplication(self.runtime)
        principal = DemoPrincipal(self.identity, self.device, self.credential)
        server = CoreHttpServer(application, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://{server.address[0]}:{server.address[1]}"

        def request(method: str, path: str, payload: dict[str, object] | None = None, headers: dict[str, str] | None = None) -> tuple[int, dict[str, object]]:
            encoded = json.dumps(payload).encode() if payload is not None else None
            request_object = Request(base + path, data=encoded, method=method, headers={"Content-Type": "application/json", **(headers or {})} if encoded else (headers or {}))
            with urlopen(request_object) as response:
                decoded = response.read().decode("utf-8")
                return response.status, json.loads(decoded) if decoded else {}

        auth = {"credential": principal.credential, "device_id": principal.device.device_id, "identity_id": principal.identity.identity_id}
        auth_headers = {"Authorization": f"Bearer {auth['credential']}", "X-JARVIS-Device-ID": auth["device_id"], "X-JARVIS-Identity-ID": auth["identity_id"]}
        try:
            status, devices = request("GET", f"/v1/devices?owner_id={principal.identity.owner_id}", headers=auth_headers)
            self.assertEqual(status, 200)
            self.assertTrue(devices["devices"])
            status, action = request("POST", "/v1/computer/actions", {**auth, "action": "list_processes", "dry_run": True})
            self.assertEqual(status, 200)
            self.assertEqual(action["status"], "succeeded")
            status, created = request("POST", "/v1/notifications", {**auth, "title": "Ready", "message": "Phase 04 ready"})
            self.assertEqual(status, 201)
            self.assertEqual(created["title"], "Ready")
            status, capabilities = request("GET", "/v1/capabilities", headers=auth_headers)
            self.assertEqual(status, 200)
            self.assertTrue(capabilities["capabilities"])
        finally:
            server.shutdown()
