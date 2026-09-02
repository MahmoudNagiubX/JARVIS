"""Tests for Phase 17 final closure: runtime bootstrap, API routes, and single authority integrity."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from jarvis.api.core import CoreApplication
from jarvis.bootstrap import create_runtime
from jarvis.config import JarvisConfig
from jarvis.contracts import (
    DeviceEnrollmentRequest,
    DeviceRole,
    DeviceStatus,
    NodeRole,
    NodeStatus,
    VoiceEndpoint,
)


class TestPhaseSeventeenFinalClosure(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.config = JarvisConfig(environment="test", runtime_role="core", database_path=":memory:")
        self.rt = create_runtime(self.config)
        self.app = CoreApplication(self.rt)

    async def test_runtime_bootstrap_phase_seventeen_services(self):
        principal = await self.app.ensure_demo_principal()
        owner_id = principal.identity.owner_id

        # Verify single authority components present
        self.assertIsNotNone(self.rt.venom)
        self.assertIsNotNone(self.rt.rooms)
        self.assertIsNotNone(self.rt.room_voice)
        self.assertIsNotNone(self.rt.device_fabric)
        self.assertIsNotNone(self.rt.voice_routing)

        # Verify experience state includes Phase 17 fields
        state = await self.app.experience_state(owner_id)
        self.assertIn("devices", state)
        self.assertIn("venom", state)
        self.assertIn("rooms", state)
        self.assertIn("fabric_diagnostics", state)
        self.assertEqual(state["venom"]["version"], "phase17")
        self.assertGreaterEqual(len(state["rooms"]), 5)

    async def test_device_enrollment_api_flow(self):
        principal = await self.app.ensure_demo_principal()
        owner_id = principal.identity.owner_id

        # Issue ticket via API
        ticket_payload = {
            "name": "Workshop Satellite",
            "role": "room_satellite",
            "platform": "windows",
            "capabilities": ["voice.input", "voice.output"],
            "ttl_minutes": 10,
        }
        ticket = await self.app.issue_device_enrollment_ticket(owner_id, ticket_payload)
        self.assertTrue(ticket["ticket_id"].startswith("ticket-"))
        self.assertTrue(bool(ticket["code"]))

        # Enroll via API
        enroll_payload = {
            "code": ticket["code"],
            "device_id": "sat-workshop-01",
            "name": "Workshop Satellite",
            "platform": "windows",
            "capabilities": ["voice.input", "voice.output"],
        }
        enrolled = await self.app.enroll_device(enroll_payload)
        self.assertTrue(enrolled["accepted"])
        self.assertEqual(enrolled["device_id"], "sat-workshop-01")
        self.assertIsNotNone(enrolled["credential"])

        # Check fabric diagnostics
        diag = await self.app.fabric_diagnostics(owner_id)
        self.assertGreaterEqual(diag["total_devices"], 1)

    async def test_device_revocation_propagation(self):
        principal = await self.app.ensure_demo_principal()
        owner_id = principal.identity.owner_id

        # Enroll a test device
        ticket = await self.app.issue_device_enrollment_ticket(owner_id, {"name": "Temp Device", "role": "room_satellite"})
        enrolled = await self.app.enroll_device({"code": ticket["code"], "device_id": "dev-temp-01", "name": "Temp Device"})
        self.assertTrue(enrolled["accepted"])

        # Revoke device via API
        revoked = await self.app.revoke_device(owner_id, "dev-temp-01")
        self.assertEqual(revoked["status"], DeviceStatus.REVOKED.value)

        # Verify device presence is cleared
        pres = await self.rt.presence.snapshot(owner_id)
        self.assertFalse(any(obs.device_id == "dev-temp-01" for obs in pres.observations))

    async def test_venom_health_and_plan_api(self):
        health = self.app.venom_detailed_health()
        self.assertEqual(health["version"], "phase17")
        self.assertEqual(health["node_id"], "venom")

        plan = self.app.venom_plan()
        self.assertFalse(plan["heavy_inference"])

    async def test_room_voice_api(self):
        principal = await self.app.ensure_demo_principal()
        owner_id = principal.identity.owner_id

        # Register voice endpoint
        ep = await self.rt.voice_routing.register(
            owner_id,
            VoiceEndpoint("ep-api-test", principal.device.device_id, "office", input_enabled=True, output_enabled=True, online=True, owner_id=owner_id)
        )

        # Utterance
        utterance_payload = {
            "session_id": "sess-api-voice",
            "endpoint_id": "ep-api-test",
            "room_id": "office",
            "text": "Hello Jarvis from room",
        }
        result = await self.app.handle_room_voice_utterance(utterance_payload, owner_id=owner_id)
        self.assertEqual(result["session_id"], "sess-api-voice")
        self.assertEqual(result["endpoint_id"], "ep-api-test")

        # Barge-in
        barge_result = await self.app.room_voice_barge_in({"session_id": "sess-api-voice", "endpoint_id": "ep-api-test"}, owner_id=owner_id)
        self.assertTrue(barge_result["barge_in"])


if __name__ == "__main__":
    unittest.main()
