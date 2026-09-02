"""Tests for Phase 17 Room fabric, presence fusion, and multi-room voice routing."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from jarvis.bus import InMemoryEventBus
from jarvis.contracts import (
    PresenceObservation,
    PresenceSnapshot,
    PresenceSource,
    RoomPlaybackEnvelope,
    RoomUtteranceEnvelope,
    RoomVoiceBargeIn,
    VoiceEndpoint,
    VoiceSessionState,
    VoiceTranscript,
    VoiceTurnResult,
)
from jarvis.devices.room.service import RoomService
from jarvis.persistence.db import SQLiteDatabase
from jarvis.persistence.repositories import RuntimeRepository
from jarvis.voice.fabric import RoomVoiceFabric
from jarvis.voice.routing.service import VoiceRoutingService


class FakeVoiceCore:
    def __init__(self):
        self.stt = None
        self.tts = None
        self.state = VoiceSessionState.IDLE
        self.last_handled = None
        self.stopped = False

    async def handle_transcript(self, transcript: VoiceTranscript, session_id: str = "voice-test") -> VoiceTurnResult:
        self.last_handled = transcript.text
        return VoiceTurnResult(transcript, f"Echo: {transcript.text}", "run-1", VoiceSessionState.IDLE)

    async def stop(self):
        self.stopped = True


class TestPhaseSeventeenRoomVoice(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = SQLiteDatabase(":memory:")
        self.repo = RuntimeRepository(self.db)
        self.bus = InMemoryEventBus()
        self.owner_id = self.repo.create_owner("Owner One")
        self.room_svc = RoomService(self.repo, self.bus)
        self.voice_routing = VoiceRoutingService(self.repo, self.bus)
        self.voice_core = FakeVoiceCore()
        self.fabric = RoomVoiceFabric(self.voice_core, self.voice_routing, self.repo, self.bus, rooms=self.room_svc)

    async def test_room_service_lifecycle_and_bindings(self):
        rooms = await self.room_svc.initialize_defaults(self.owner_id)
        self.assertGreaterEqual(len(rooms), 5)
        self.assertTrue(any(r.room_id == "office" for r in rooms))

        # Bind device, voice endpoint, and home entity
        await self.room_svc.bind_device(self.owner_id, "office", "dev-pc")
        await self.room_svc.bind_voice_endpoint(self.owner_id, "office", "ep-mic-office")
        await self.room_svc.bind_home_entity(self.owner_id, "office", "light.office_desk")

        office = await self.room_svc.get_room(self.owner_id, "office")
        self.assertIn("dev-pc", office.devices)
        self.assertIn("ep-mic-office", office.voice_endpoints)
        self.assertIn("light.office_desk", office.home_entities)

        snap = await self.room_svc.snapshot(self.owner_id, "office")
        self.assertEqual(snap.device_count, 1)
        self.assertEqual(snap.entity_count, 1)

    async def test_voice_routing_and_revocation(self):
        # Register room endpoints
        ep1 = VoiceEndpoint("ep-office", "dev-pc", "office", input_enabled=True, output_enabled=True, online=True, owner_id=self.owner_id)
        ep2 = VoiceEndpoint("ep-living", "dev-tv", "living_room", input_enabled=True, output_enabled=True, online=True, owner_id=self.owner_id)
        await self.voice_routing.register(self.owner_id, ep1)
        await self.voice_routing.register(self.owner_id, ep2)

        # Route from office returns to office
        route = await self.voice_routing.select(self.owner_id, "sess-1", "ep-office")
        self.assertEqual(route.output_endpoint_id, "ep-office")
        self.assertFalse(route.handoff)

        # Revoke device endpoints
        revoked = await self.voice_routing.revoke_device_endpoints(self.owner_id, "dev-pc")
        self.assertEqual(len(revoked), 1)
        self.assertFalse(revoked[0].online)

        # Selecting revoked endpoint raises error
        with self.assertRaises(ValueError):
            await self.voice_routing.select(self.owner_id, "sess-2", "ep-office")

    async def test_room_voice_fabric_multi_room_utterance(self):
        ep = VoiceEndpoint("ep-lab", "dev-lab", "lab", input_enabled=True, output_enabled=True, online=True, owner_id=self.owner_id)
        await self.voice_routing.register(self.owner_id, ep)

        envelope = RoomUtteranceEnvelope(
            session_id="sess-voice-lab",
            endpoint_id="ep-lab",
            room_id="lab",
            text="Jarvis, initiate test sequence",
            owner_id=self.owner_id,
        )
        playback = await self.fabric.handle_room_utterance(envelope, owner_id=self.owner_id)
        self.assertEqual(playback.endpoint_id, "ep-lab")
        self.assertEqual(playback.text, "Echo: Jarvis, initiate test sequence")
        self.assertFalse(playback.interrupted)

    async def test_room_voice_barge_in(self):
        # Record turn in flight with matching owner
        self.fabric._in_flight["sess-active"] = {
            "turn_id": "t1",
            "owner_id": self.owner_id,
            "endpoint_id": "ep-lab",
            "room_id": "lab",
            "started_at": datetime.now(UTC),
            "cancelled": False,
        }
        barge = RoomVoiceBargeIn("sess-active", "ep-lab", "lab", datetime.now(UTC), "barge_in")
        ok = await self.fabric.barge_in(barge, owner_id=self.owner_id)
        self.assertTrue(ok)
        self.assertTrue(self.voice_core.stopped)

    async def test_room_voice_barge_in_wrong_owner_fails_closed(self):
        # Turn started by self.owner_id
        self.fabric._in_flight["sess-owner-turn"] = {
            "turn_id": "t2",
            "owner_id": self.owner_id,
            "endpoint_id": "ep-lab",
            "room_id": "lab",
            "started_at": datetime.now(UTC),
            "cancelled": False,
        }
        self.voice_core.stopped = False

        # Attempt barge-in from a different owner
        other_owner = self.repo.create_owner("Attacker Owner")
        barge = RoomVoiceBargeIn("sess-owner-turn", "ep-lab", "lab", datetime.now(UTC), "barge_in")
        ok = await self.fabric.barge_in(barge, owner_id=other_owner)

        # Must fail closed and not cancel the original owner's turn
        self.assertFalse(ok)
        self.assertFalse(self.fabric._in_flight["sess-owner-turn"]["cancelled"])
        self.assertFalse(self.voice_core.stopped)

    async def test_room_voice_barge_in_no_flight_wrong_or_unknown_endpoint_fails_closed(self):
        # Ensure no flight exists in self.fabric._in_flight
        self.fabric._in_flight.clear()
        self.voice_core.stopped = False

        # Create another owner and register an endpoint for that other owner
        other_owner = self.repo.create_owner("Victim Owner")
        ep_victim = VoiceEndpoint("ep-victim", "dev-victim", "office", input_enabled=True, output_enabled=True, online=True, owner_id=other_owner)
        await self.voice_routing.register(other_owner, ep_victim)

        # 1. Attacker calls barge_in with no flight targeting the other owner's endpoint
        barge_wrong_owner = RoomVoiceBargeIn("sess-arbitrary", "ep-victim", "office", datetime.now(UTC), "barge_in")
        ok1 = await self.fabric.barge_in(barge_wrong_owner, owner_id=self.owner_id)
        self.assertFalse(ok1)
        self.assertFalse(self.voice_core.stopped)

        # 2. Attacker calls barge_in with an unknown non-existent endpoint
        barge_unknown_ep = RoomVoiceBargeIn("sess-arbitrary-2", "ep-ghost-nonexistent", "office", datetime.now(UTC), "barge_in")
        ok2 = await self.fabric.barge_in(barge_unknown_ep, owner_id=self.owner_id)
        self.assertFalse(ok2)
        self.assertFalse(self.voice_core.stopped)

        # 3. Legitimate owner calls barge_in on their own valid registered endpoint with no active flight -> succeeds
        ep_legit = VoiceEndpoint("ep-legit", "dev-legit", "office", input_enabled=True, output_enabled=True, online=True, owner_id=self.owner_id)
        await self.voice_routing.register(self.owner_id, ep_legit)
        barge_valid = RoomVoiceBargeIn("sess-legit", "ep-legit", "office", datetime.now(UTC), "barge_in")
        ok3 = await self.fabric.barge_in(barge_valid, owner_id=self.owner_id)
        self.assertTrue(ok3)
        self.assertTrue(self.voice_core.stopped)

    async def test_room_utterance_unregistered_device_fails_closed_and_creates_no_device_row(self):
        # Fake real VoiceCore with process_transcript
        class RealishVoiceCore(FakeVoiceCore):
            def __init__(self):
                super().__init__()
                self.context = None

            async def start(self, context):
                self.context = context

            async def process_transcript(self, transcript, identity, device):
                return VoiceTurnResult(transcript, "Processed", "run-1", VoiceSessionState.IDLE)

        realish_core = RealishVoiceCore()
        fabric_with_real_core = RoomVoiceFabric(realish_core, self.voice_routing, self.repo, self.bus, rooms=self.room_svc)

        # ep-unreg references dev-unregistered, which does NOT exist in self.repo.devices
        ep = VoiceEndpoint("ep-unreg", "dev-unregistered", "lab", input_enabled=True, output_enabled=True, online=True, owner_id=self.owner_id)
        await self.voice_routing.register(self.owner_id, ep)
        self.assertIsNone(self.repo.device("dev-unregistered"))

        envelope = RoomUtteranceEnvelope(
            session_id="sess-unreg",
            endpoint_id="ep-unreg",
            room_id="lab",
            text="Hello unauthorized",
            owner_id=self.owner_id,
        )

        with self.assertRaises(PermissionError):
            await fabric_with_real_core.handle_room_utterance(envelope, owner_id=self.owner_id)

        # Verify RoomVoiceFabric DID NOT synthesize a row into devices table!
        self.assertIsNone(self.repo.device("dev-unregistered"))


    async def test_room_service_restart_durability_across_new_instances(self):
        # Create room and bindings in self.room_svc
        room = await self.room_svc.create_room(self.owner_id, "Workshop", room_id="workshop")
        await self.room_svc.bind_device(self.owner_id, "workshop", "dev-3d-printer")
        await self.room_svc.bind_voice_endpoint(self.owner_id, "workshop", "ep-workshop-mic")
        await self.room_svc.bind_home_entity(self.owner_id, "workshop", "switch.soldering_station")

        # Now simulate restart: create a brand new RoomService over the same repository
        new_bus = InMemoryEventBus()
        restarted_service = RoomService(self.repo, new_bus)

        # Verify room and all bindings persisted
        recovered = await restarted_service.get_room(self.owner_id, "workshop")
        self.assertIsNotNone(recovered)
        self.assertEqual(recovered.name, "Workshop")
        self.assertIn("dev-3d-printer", recovered.devices)
        self.assertIn("ep-workshop-mic", recovered.voice_endpoints)
        self.assertIn("switch.soldering_station", recovered.home_entities)

        all_rooms = await restarted_service.list_rooms(self.owner_id)
        self.assertTrue(any(r.room_id == "workshop" for r in all_rooms))

    async def test_voice_routing_service_restart_durability_and_state_preservation(self):
        # Register ep1 (online, input=True, output=True), ep2 (offline, input=False, output=True)
        ep1 = VoiceEndpoint("ep-persisted-1", "dev-1", "office", input_enabled=True, output_enabled=True, online=True, owner_id=self.owner_id)
        ep2 = VoiceEndpoint("ep-persisted-2", "dev-2", "bedroom", input_enabled=False, output_enabled=True, online=True, owner_id=self.owner_id)
        await self.voice_routing.register(self.owner_id, ep1)
        await self.voice_routing.register(self.owner_id, ep2)

        # Set ep2 to offline
        await self.voice_routing.set_online(self.owner_id, "ep-persisted-2", False)

        # Create another owner with their own endpoint for isolation check
        other_owner = self.repo.create_owner("Other Owner")
        ep_other = VoiceEndpoint("ep-other", "dev-other", "kitchen", input_enabled=True, output_enabled=True, online=True, owner_id=other_owner)
        await self.voice_routing.register(other_owner, ep_other)

        # Revoke an endpoint
        ep_rev = VoiceEndpoint("ep-to-revoke", "dev-rev", "lab", input_enabled=True, output_enabled=True, online=True, owner_id=self.owner_id)
        await self.voice_routing.register(self.owner_id, ep_rev)
        await self.voice_routing.revoke_endpoint(self.owner_id, "ep-to-revoke")

        # Now simulate restart with brand new VoiceRoutingService over the same repository
        new_bus = InMemoryEventBus()
        restarted_routing = VoiceRoutingService(self.repo, new_bus)

        # Recover ep1 -> must be online with input/output enabled
        rec1 = await restarted_routing.get(self.owner_id, "ep-persisted-1")
        self.assertIsNotNone(rec1)
        self.assertTrue(rec1.online)
        self.assertTrue(rec1.input_enabled)
        self.assertTrue(rec1.output_enabled)
        self.assertEqual(rec1.room_id, "office")

        # Recover ep2 -> must remain OFFLINE, NOT resurrected as online!
        rec2 = await restarted_routing.get(self.owner_id, "ep-persisted-2")
        self.assertIsNotNone(rec2)
        self.assertFalse(rec2.online)
        self.assertFalse(rec2.input_enabled)
        self.assertTrue(rec2.output_enabled)

        # Recover revoked ep -> must remain offline and muted (not active)
        rec_rev = await restarted_routing.get(self.owner_id, "ep-to-revoke")
        self.assertIsNotNone(rec_rev)
        self.assertFalse(rec_rev.online)
        self.assertFalse(rec_rev.input_enabled)
        self.assertFalse(rec_rev.output_enabled)

        # Owner isolation: self.owner_id cannot list or get other_owner endpoints
        self.assertIsNone(await restarted_routing.get(self.owner_id, "ep-other"))
        my_eps = await restarted_routing.list(self.owner_id)
        self.assertFalse(any(e.endpoint_id == "ep-other" for e in my_eps))

    async def test_room_service_save_room_error_handling_fails_closed(self):
        # If repository throws during save, create_room should raise and not pretend durable success
        original_set = self.repo.set_personalization
        def fail_set(*args, **kwargs):
            raise RuntimeError("Database write failure")
        self.repo.set_personalization = fail_set

        with self.assertRaises(RuntimeError):
            await self.room_svc.create_room(self.owner_id, "Fail Room", room_id="fail_room")

        self.repo.set_personalization = original_set

    async def test_room_service_load_repository_error_fails_closed(self):
        # Recreating RoomService on a broken repo should fail-closed and raise, not pretend empty layout
        new_svc = RoomService(self.repo, InMemoryEventBus())
        original_pers = self.repo.personalization
        def fail_pers(*args, **kwargs):
            raise RuntimeError("Database read connection lost")
        self.repo.personalization = fail_pers

        with self.assertRaises(RuntimeError):
            await new_svc.list_rooms(self.owner_id)

        with self.assertRaises(RuntimeError):
            await new_svc.get_room(self.owner_id, "office")

        self.repo.personalization = original_pers

    async def test_room_service_failed_save_leaves_no_phantom_in_memory_state(self):
        # If _save_room fails during create_room, in-memory state must NOT retain the phantom room
        original_set = self.repo.set_personalization
        def fail_set(*args, **kwargs):
            raise RuntimeError("Storage write failed")
        self.repo.set_personalization = fail_set

        with self.assertRaises(RuntimeError):
            await self.room_svc.create_room(self.owner_id, "Phantom Room", room_id="phantom_room")

        self.repo.set_personalization = original_set
        self.assertIsNone(await self.room_svc.get_room(self.owner_id, "phantom_room"))

        # Successfully create a room
        await self.room_svc.create_room(self.owner_id, "Real Room", room_id="real_room")

        # Now fail save during bind_device -> must NOT leave phantom device bound in memory
        self.repo.set_personalization = fail_set
        with self.assertRaises(RuntimeError):
            await self.room_svc.bind_device(self.owner_id, "real_room", "dev-phantom")

        self.repo.set_personalization = original_set
        real = await self.room_svc.get_room(self.owner_id, "real_room")
        self.assertIsNotNone(real)
        self.assertNotIn("dev-phantom", real.devices)


if __name__ == "__main__":
    unittest.main()
