from __future__ import annotations

import unittest
import asyncio
import threading
from http import HTTPStatus
from datetime import UTC, datetime, timedelta
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from jarvis.api.core import CoreApplication
from jarvis.api.http import CoreHttpServer
from jarvis.attention.policy import AttentionContext
from jarvis.authority.identity.service import EnrollmentGrant
from jarvis.bootstrap import create_runtime
from jarvis.config import JarvisConfig
from jarvis.contracts import HomeAction, HomeEntity, Notification, VoiceEndpoint, VoiceSessionContext, VoiceSessionState, VoiceTranscript
from jarvis.devices.home.service import InMemoryHomeTransport
from jarvis.notifications.delivery import NotificationDeliveryCoordinator
from jarvis.presence.service import PresenceObservation


class PhaseEightIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:"))
        await self.runtime.start()
        self.identity = await self.runtime.identity.bootstrap_owner("Phase Eight Owner")
        enrollment = await self.runtime.identity.create_enrollment(EnrollmentGrant(
            self.identity.owner_id, "Phase Eight Device", "desktop", "windows", ("tool.request",),
            ("home.read", "home.control", "computer.observe"),
        ))
        issued = await self.runtime.identity.redeem_enrollment(enrollment.code)
        self.device = await self.runtime.identity.authenticate(issued.raw, issued.device_id)
        assert self.device is not None

    async def asyncTearDown(self) -> None:
        await self.runtime.shutdown()

    async def test_presence_is_evidence_backed_and_expires(self) -> None:
        observed = datetime.now(UTC)
        await self.runtime.presence.observe(PresenceObservation(
            "presence-test", self.identity.owner_id, "originating_device", observed,
            self.device.device_id, "office", "desk-voice", 0.95, 1,
        ))
        current = await self.runtime.presence.snapshot(self.identity.owner_id, now=observed + timedelta(milliseconds=200))
        self.assertEqual(current.room_id, "office")
        self.assertEqual(current.active_device_id, self.device.device_id)
        await self.runtime.presence.expire(self.identity.owner_id, now=observed + timedelta(seconds=2))
        expired = await self.runtime.presence.snapshot(self.identity.owner_id, now=observed + timedelta(seconds=2))
        self.assertIsNone(expired.active_device_id)
        self.assertFalse(self.runtime.repository.memories(self.identity.owner_id))

    async def test_attention_modes_queue_low_priority_without_granting_authority(self) -> None:
        item = Notification("notification-test", "Info", "A local update", "info", "test", owner_id=self.identity.owner_id)
        presence = await self.runtime.presence.snapshot(self.identity.owner_id)
        decision = self.runtime.attention.decide(item, presence, AttentionContext(mode="focus"))
        self.assertTrue(decision.queue)
        self.assertTrue(decision.visual_only)
        critical = self.runtime.attention.decide(Notification("critical", "Critical", "Immediate", "critical", "test", owner_id=self.identity.owner_id), presence, AttentionContext(mode="focus"))
        self.assertTrue(critical.escalate)
        self.assertFalse(critical.voice_only)

    async def test_personal_operations_and_focus_are_bounded(self) -> None:
        result = await self.runtime.operations.run(self.identity.owner_id, "work_start")
        self.assertEqual(result.overall_status, "completed")
        self.assertEqual((await self.runtime.operations.mode(self.identity.owner_id)).mode, "work")
        focus = await self.runtime.operations.start_focus(self.identity.owner_id, duration_seconds=30)
        self.assertEqual(focus.status, "active")
        ended = await self.runtime.operations.end_focus(self.identity.owner_id)
        self.assertEqual(ended.status, "completed")
        self.assertEqual((await self.runtime.operations.mode(self.identity.owner_id)).mode, "normal")

    async def test_followups_and_auto_send_rules_are_scoped_and_anti_loop(self) -> None:
        followup = await self.runtime.communication_followups.create(self.identity.owner_id, "thread-1", delay_seconds=1)
        due = await self.runtime.communication_followups.due(self.identity.owner_id, now=followup.due_at + timedelta(seconds=1))
        self.assertEqual(due[0].status, "due")
        await self.runtime.communication_followups.acknowledge(self.identity.owner_id, followup.followup_id)
        await self.runtime.communication_followups.create_rule(self.identity.owner_id, {
            "channel": "local", "recipient_allowlist": ["owner"], "message_class": "normal",
            "approval_requirement": "none", "max_frequency": 1,
        })
        allowed, _ = self.runtime.communication_followups.can_auto_send_scoped(self.identity.owner_id, "local", "owner", "hello")
        blocked, reason = self.runtime.communication_followups.can_auto_send_scoped(self.identity.owner_id, "local", "owner", "hello")
        self.assertTrue(allowed)
        self.assertFalse(blocked)
        self.assertEqual(reason, "rate_limited")

    async def test_home_context_and_safe_routine_delegate_to_home_authority(self) -> None:
        self.runtime.home.transport = InMemoryHomeTransport((HomeEntity("light.office", "Office", "light", "off", {}, "office"),))
        context = await self.runtime.home_context.refresh(self.identity, self.device)
        self.assertTrue(context.available)
        self.assertEqual(len(context.entities), 1)
        run = await self.runtime.home_routines.run("focus_lighting", self.identity, self.device, dry_run=True)
        self.assertEqual(run.status, "completed")
        blocked = await self.runtime.home.execute(HomeAction("lock.front", "lock", dry_run=False), self.identity, self.device)
        self.assertEqual(blocked.error_code, "home_action_blocked")

    async def test_delivery_reports_unavailable_surfaces_and_suppresses_duplicate_voice(self) -> None:
        endpoint = await self.runtime.voice_routing.register(self.identity.owner_id, VoiceEndpoint("voice-office", self.device.device_id, "office"))
        await self.runtime.presence.observe(PresenceObservation("voice-presence", self.identity.owner_id, "voice_endpoint", datetime.now(UTC), self.device.device_id, "office", endpoint.endpoint_id, 1, 300))
        item = await self.runtime.notifications.create(self.identity.owner_id, "Build", "Done", severity="important")
        first = await self.runtime.notification_delivery.deliver(self.identity.owner_id, item)
        self.assertEqual(first.status, "delivered")
        self.assertIn("hud", first.channels)
        self.assertTrue(any(attempt.status == "unavailable" for attempt in first.attempts))

    async def test_voice_follow_up_window_expires_without_indefinite_capture(self) -> None:
        self.runtime.voice.follow_up_seconds = 0.01
        session = self.runtime.repository.create_session(self.identity.owner_id, self.device.device_id)
        conversation = self.runtime.repository.create_conversation(self.identity.owner_id, self.device.device_id, None)
        await self.runtime.voice.start(VoiceSessionContext(session.id, self.device.device_id, room_id="office", owner_id=self.identity.owner_id, endpoint_id="voice-office", conversation_id=conversation.id))
        result = await self.runtime.voice.process_transcript(VoiceTranscript("hello", True, "en"), self.identity, self.device)
        self.assertEqual(result.state, VoiceSessionState.FOLLOW_UP)
        await asyncio.sleep(0.03)
        self.assertEqual(self.runtime.voice.state, VoiceSessionState.LISTENING)

    async def test_phase_eight_gets_are_private_and_public_allowlist_is_exact(self) -> None:
        server = CoreHttpServer(CoreApplication(self.runtime), port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://{server.address[0]}:{server.address[1]}"
        auth_headers = {"Authorization": "Bearer test-placeholder", "X-JARVIS-Device-ID": self.device.device_id, "X-JARVIS-Identity-ID": self.identity.identity_id}
        private = ("/presence", "/attention", "/personal-operations/modes", "/focus", "/communications/follow-ups", "/communications/auto-send-rules", "/home/context", "/routines")
        try:
            for route in private:
                with self.assertRaises(HTTPError) as error:
                    urlopen(Request(base + "/v1" + route), timeout=3)
                self.assertEqual(error.exception.code, HTTPStatus.UNAUTHORIZED)
            for route in ("/health", "/hud", "/experience/hud"):
                request = Request(base + "/v1" + route, headers=auth_headers)
                with urlopen(request, timeout=3) as response:
                    self.assertEqual(response.status, HTTPStatus.OK)
        finally:
            server.shutdown()
