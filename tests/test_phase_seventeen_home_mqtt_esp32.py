"""Tests for Phase 17 Home Assistant, Restricted MQTT, and ESP32 protocol contracts."""

from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime, timedelta
from jarvis.authority.approvals.service import DurableApprovalEngine
from jarvis.authority.audit.service import DurableAuditService
from jarvis.authority.permissions.engine import PolicyPermissionEngine
from jarvis.bus import InMemoryEventBus
from jarvis.contracts import (
    DeviceIdentity,
    ESP32CommandEnvelope,
    HomeAction,
    HomeEntity,
    HomeEntityMapping,
    Identity,
)
from jarvis.devices.home.service import (
    HomeActionService,
    InMemoryHomeTransport,
    RestrictedMQTTTransport,
)
from jarvis.persistence.db import SQLiteDatabase
from jarvis.persistence.repositories import RuntimeRepository


class TestPhaseSeventeenHomeMqttEsp32(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = SQLiteDatabase(":memory:")
        self.repo = RuntimeRepository(self.db)
        self.bus = InMemoryEventBus()
        self.permission = PolicyPermissionEngine()
        self.audit = DurableAuditService(self.repo)
        self.approval = DurableApprovalEngine(self.repo)
        self.owner_id = self.repo.create_owner("Owner One")
        self.identity = Identity(identity_id="ident-1", display_name="Owner", owner_id=self.owner_id, roles=frozenset({"owner"}))
        self.device = DeviceIdentity(
            device_id="dev-1",
            owner_id=self.owner_id,
            device_kind="desktop",
            platform="windows",
            capabilities=frozenset({"home.read", "home.control"}),
            scopes=frozenset({"tool.request"}),
        )
        self.transport = InMemoryHomeTransport((
            HomeEntity("light.living_room", "Living Room Light", "light", "off", {"brightness": 0}, "living_room"),
            HomeEntity("climate.main_thermostat", "Main Thermostat", "climate", "cool", {"temperature": 22}, "living_room"),
        ))
        self.mqtt = RestrictedMQTTTransport(allowed_prefixes=(f"jarvis/{self.owner_id}/", "home/"))
        self.service = HomeActionService(self.transport, self.repo, self.bus, self.permission, self.audit, mqtt=self.mqtt, approval=self.approval)

    async def test_home_action_safe_allowlist(self):
        res = await self.service.execute(HomeAction("light.living_room", "turn_on", {"brightness": 80}, dry_run=False), self.identity, self.device)
        self.assertEqual(res.status, "succeeded")
        self.assertEqual(self.transport.entities["light.living_room"].state, "on")

        res_off = await self.service.execute(HomeAction("light.living_room", "turn_off", dry_run=False), self.identity, self.device)
        self.assertEqual(res_off.status, "succeeded")
        self.assertEqual(self.transport.entities["light.living_room"].state, "off")

        # Valid set_color succeeds
        res_color = await self.service.execute(HomeAction("light.living_room", "set_color", {"color": "blue"}, dry_run=False), self.identity, self.device)
        self.assertEqual(res_color.status, "succeeded")
        self.assertEqual(self.transport.entities["light.living_room"].attributes.get("color"), "blue")

        # Blank set_color denied with color_invalid
        res_blank = await self.service.execute(HomeAction("light.living_room", "set_color", {"color": "   "}, dry_run=False), self.identity, self.device)
        self.assertEqual(res_blank.status, "denied")
        self.assertEqual(res_blank.error_code, "color_invalid")

        # Non-string set_color denied with color_invalid
        res_nonstr = await self.service.execute(HomeAction("light.living_room", "set_color", {"color": 123}, dry_run=False), self.identity, self.device)
        self.assertEqual(res_nonstr.status, "denied")
        self.assertEqual(res_nonstr.error_code, "color_invalid")

    async def test_home_action_blocked_dangerous_actions(self):
        for dangerous in ("lock", "unlock", "alarm", "security_override", "raw_shell"):
            res = await self.service.execute(HomeAction("lock.front_door", dangerous, dry_run=False), self.identity, self.device)
            self.assertEqual(res.status, "denied")
            self.assertEqual(res.error_code, "home_action_blocked")

    async def test_home_action_temperature_extreme_requires_approval(self):
        # Normal temperature range: 15 to 30 -> succeeds
        res_normal = await self.service.execute(HomeAction("climate.main_thermostat", "set_temperature", {"temperature": 23}, dry_run=False), self.identity, self.device)
        self.assertEqual(res_normal.status, "succeeded")

        # Extreme temperature -> requires approval
        res_extreme = await self.service.execute(HomeAction("climate.main_thermostat", "set_temperature", {"temperature": 45}, dry_run=False), self.identity, self.device)
        self.assertEqual(res_extreme.status, "approval_required")
        self.assertEqual(res_extreme.error_code, "extreme_temperature_requires_approval")

    async def test_restricted_mqtt_transport_and_esp32_parsing(self):
        mqtt = RestrictedMQTTTransport(allowed_prefixes=(f"jarvis/{self.owner_id}/",))

        # Out of scope topic -> rejected
        allowed = await mqtt.publish("evil/topic", json.dumps({"cmd": "hack"}))
        self.assertFalse(allowed)

        # Allowed topic with no publisher -> returns False, not configured, zero published messages recorded
        self.assertFalse(mqtt.configured)
        allowed_no_pub = await mqtt.publish(f"jarvis/{self.owner_id}/dev-esp/command/relay", json.dumps({"action": "toggle"}))
        self.assertFalse(allowed_no_pub)
        self.assertEqual(mqtt.published, [])

        # Configured publisher returning True -> returns True and records message
        configured_mqtt = RestrictedMQTTTransport(publisher=lambda t, p: True, allowed_prefixes=(f"jarvis/{self.owner_id}/",))
        self.assertTrue(configured_mqtt.configured)
        ok_pub = await configured_mqtt.publish(f"jarvis/{self.owner_id}/dev-esp/command/relay", json.dumps({"action": "toggle"}))
        self.assertTrue(ok_pub)
        self.assertEqual(len(configured_mqtt.published), 1)

        # Configured publisher returning False -> returns False and does not record
        failing_mqtt = RestrictedMQTTTransport(publisher=lambda t, p: False, allowed_prefixes=(f"jarvis/{self.owner_id}/",))
        fail_pub = await failing_mqtt.publish(f"jarvis/{self.owner_id}/dev-esp/command/relay", json.dumps({"action": "toggle"}))
        self.assertFalse(fail_pub)
        self.assertEqual(failing_mqtt.published, [])

        # Retained command topic -> rejected
        allowed_retain = await configured_mqtt.publish(f"jarvis/{self.owner_id}/dev-esp/command/relay", json.dumps({"action": "toggle"}), retain=True)
        self.assertFalse(allowed_retain)

        # Valid telemetry state parsing
        state_payload = json.dumps({"temperature": 24.5, "humidity": 55.0, "online": True})
        state_env = mqtt.parse_esp32_state(f"jarvis/{self.owner_id}/dev-esp/state/dht22", state_payload)
        self.assertIsNotNone(state_env)
        self.assertEqual(state_env.device_id, "dev-esp")
        self.assertEqual(state_env.target, "dht22")
        self.assertEqual(state_env.state["temperature"], 24.5)

        # Valid command parsing
        future_time = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
        cmd_payload = json.dumps({"command_id": "cmd-1", "action": "set_level", "parameters": {"level": 50}, "expires_at": future_time})
        cmd_env = mqtt.parse_esp32_command(f"jarvis/{self.owner_id}/dev-esp/command/led", cmd_payload)
        self.assertIsNotNone(cmd_env)
        self.assertEqual(cmd_env.command_id, "cmd-1")
        self.assertEqual(cmd_env.action, "set_level")

        # Expired command parsing -> discarded
        past_time = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
        stale_payload = json.dumps({"command_id": "cmd-old", "action": "set_level", "expires_at": past_time})
        stale_env = mqtt.parse_esp32_command(f"jarvis/{self.owner_id}/dev-esp/command/led", stale_payload)
        self.assertIsNone(stale_env)

    async def test_home_action_unknown_entity_denied(self):
        # Action targeting unknown unmapped entity -> denied before transport execution
        res = await self.service.execute(
            HomeAction("light.unknown_ghost_light", "turn_on", dry_run=False),
            self.identity,
            self.device,
        )
        self.assertEqual(res.status, "denied")
        self.assertEqual(res.error_code, "home_entity_unknown")

    async def test_home_action_disabled_entity_mapping_denied(self):
        mapping = HomeEntityMapping(
            entity_id="switch.garage_door",
            domain="switch",
            room_id="garage",
            read_capabilities=frozenset({"home.read"}),
            write_capabilities=frozenset({"home.control"}),
            risk_level="safe",
            enabled=False,
        )
        self.service.register_entity_mapping(mapping)
        res = await self.service.execute(
            HomeAction("switch.garage_door", "turn_on", dry_run=False),
            self.identity,
            self.device,
        )
        self.assertEqual(res.status, "denied")
        self.assertEqual(res.error_code, "home_entity_disabled")

    async def test_home_action_capability_mismatch_denied(self):
        mapping = HomeEntityMapping(
            entity_id="light.restricted_lab",
            domain="light",
            room_id="lab",
            read_capabilities=frozenset({"home.read"}),
            write_capabilities=frozenset({"special.lab.control"}),
            risk_level="safe",
            enabled=True,
        )
        self.service.register_entity_mapping(mapping)
        # Device only has {"home.read", "home.control"} -> lacks {"special.lab.control"}
        res = await self.service.execute(
            HomeAction("light.restricted_lab", "turn_on", dry_run=False),
            self.identity,
            self.device,
        )
        self.assertEqual(res.status, "denied")
        self.assertEqual(res.error_code, "device_capability_missing")

    async def test_home_action_consequential_risk_requires_approval(self):
        heater = HomeEntity("switch.water_heater", "Water Heater", "switch", "off", {}, "basement")
        self.transport.entities["switch.water_heater"] = heater
        mapping = HomeEntityMapping(
            entity_id="switch.water_heater",
            domain="switch",
            room_id="basement",
            read_caps=frozenset({"home.read"}),
            write_caps=frozenset({"home.control"}),
            risk_level="consequential",
            enabled=True,
        )
        self.service.register_entity_mapping(mapping)
        res = await self.service.execute(
            HomeAction("switch.water_heater", "turn_on", dry_run=False),
            self.identity,
            self.device,
        )
        self.assertEqual(res.status, "approval_required")
        self.assertIsNotNone(res.approval_id)
        # Verify pending approval exists in repository
        row = self.repo.approval(res.approval_id)
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "pending")
        # Entity has not turned on yet
        self.assertEqual(self.transport.entities["switch.water_heater"].state, "off")

        # Now approve it
        decide_res = await self.service.decide_approval(res.approval_id, True, self.identity.identity_id)
        self.assertEqual(decide_res.status, "succeeded")
        self.assertEqual(self.transport.entities["switch.water_heater"].state, "on")

        # Second approval execution is blocked (exactly-once)
        second_res = await self.service.decide_approval(res.approval_id, True, self.identity.identity_id)
        self.assertEqual(second_res.status, "failed")
        self.assertEqual(second_res.error_code, "pending_action_unavailable_after_restart")
    async def test_home_action_list_entities_privacy_boundary_unmapped_not_exposed(self):
        # Transport has 2 entities: mapped light and unmapped secret sensor
        mapped_entity = HomeEntity("light.authorized_lamp", "Authorized Lamp", "light", "on", {}, "living_room")
        unmapped_entity = HomeEntity("camera.unmapped_secret_cam", "Secret Cam", "camera", "streaming", {}, "bedroom")
        transport = InMemoryHomeTransport((mapped_entity, unmapped_entity))

        # Explicit production service with ONLY light.authorized_lamp mapped
        service = HomeActionService(transport, self.repo, self.bus, self.permission, self.audit)
        # Clear the auto-registered in-memory mappings to simulate explicit configuration
        service._entity_mappings.clear()
        service.register_entity_mapping(HomeEntityMapping(
            entity_id="light.authorized_lamp",
            display_name="Authorized Lamp",
            domain="light",
            room_id="living_room",
            enabled=True,
        ))

        entities = await service.list_entities(self.identity, self.device)
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0].entity_id, "light.authorized_lamp")
        self.assertFalse(any(e.entity_id == "camera.unmapped_secret_cam" for e in entities))

    async def test_home_action_late_bound_in_memory_transport_seam(self):
        # Construct HomeActionService with transport=None (as runtime bootstrap does)
        service = HomeActionService(None, self.repo, self.bus, self.permission, self.audit)

        # Later in test, assign InMemoryHomeTransport
        test_lamp = HomeEntity("light.late_bound_lamp", "Late Lamp", "light", "off", {}, "office")
        service.transport = InMemoryHomeTransport((test_lamp,))

        # Verify entity is visible and executable through in-memory test seam
        entities = await service.list_entities(self.identity, self.device)
        self.assertTrue(any(e.entity_id == "light.late_bound_lamp" for e in entities))

        res = await service.execute(
            HomeAction("light.late_bound_lamp", "turn_on", dry_run=False),
            self.identity,
            self.device,
        )
        self.assertEqual(res.status, "succeeded")


if __name__ == "__main__":
    unittest.main()
