"""Comprehensive deterministic tests for JARVIS Phase 17 Final Product & Network Closure."""

from __future__ import annotations

import asyncio
import json
import unittest
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from jarvis.api.auth import DesktopSessionService, StreamTicketService
from jarvis.api.core import CoreApplication, DemoPrincipal
from jarvis.api.node_http import CoreNodeHttpServer
from jarvis.authority.approvals.service import DurableApprovalEngine
from jarvis.authority.audit.service import DurableAuditService
from jarvis.authority.permissions.engine import PolicyPermissionEngine
from jarvis.bus import InMemoryEventBus
from jarvis.contracts import (
    ApprovalStatus,
    DeviceEnrollmentRequest,
    DeviceHeartbeat,
    DeviceIdentity,
    DeviceRecord,
    DeviceRole,
    DeviceStatus,
    HomeAction,
    HomeEntity,
    HomeEntityMapping,
    Identity,
    RoomUtteranceEnvelope,
    RoomVoiceBargeIn,
)
from jarvis.devices.satellite.contracts import (
    SatelliteCommand,
    SatelliteHello,
)
from jarvis.devices.fabric import DeviceFabricService
from jarvis.devices.home.service import (
    HomeActionService,
    InMemoryHomeTransport,
    RestrictedMQTTTransport,
)
from jarvis.devices.room.service import RoomService
from jarvis.devices.satellite.registry import WindowsSatelliteRegistry
from jarvis.devices.satellite.transport import SatelliteTransportService
from jarvis.network.validation import (
    NetworkValidationError,
    is_private_ip,
    validate_private_core_url,
)
from jarvis.nodes.venom import VenomNode
from jarvis.nodes.venom_daemon import VenomDaemon
from jarvis.persistence.db import SQLiteDatabase
from jarvis.persistence.repositories import RuntimeRepository
from jarvis.satellite_agent.agent import SatelliteAgentConfig, WindowsSatelliteAgent
from jarvis.voice.core import VoiceCore
from jarvis.voice.fabric import RoomVoiceFabric
from jarvis.voice.routing.service import VoiceRoutingService
from jarvis.world_state.service import DurableWorldStateService


class TestPhaseSeventeenNetworkClosure(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = SQLiteDatabase(":memory:")
        self.repo = RuntimeRepository(self.db)
        self.bus = InMemoryEventBus()
        self.permission = PolicyPermissionEngine()
        self.audit = DurableAuditService(self.repo)
        self.approval = DurableApprovalEngine(self.repo)
        self.world_state = DurableWorldStateService(self.repo, self.bus)

        self.owner_id = self.repo.create_owner("Mahmoud")
        ident_id = self.repo.create_identity(self.owner_id, "Mahmoud", "owner", ("owner",))
        self.identity = Identity(ident_id, "Mahmoud", self.owner_id, frozenset({"owner"}))
        self.device = DeviceIdentity(
            "dev-primary",
            self.owner_id,
            "primary_pc",
            "windows",
            frozenset({"home.read", "home.control", "voice.input", "voice.output"}),
            frozenset({"tool.request"}),
        )

        self.satellite_registry = WindowsSatelliteRegistry()
        self.satellite_transport = SatelliteTransportService(self.satellite_registry)
        self.fabric = DeviceFabricService(self.repo, self.bus, self.audit)
        self.voice_routing = VoiceRoutingService(self.repo, self.bus)
        self.rooms = RoomService(self.repo, self.bus)
        self.venom = VenomNode()

        # Dummy VoiceCore for testing
        class DummySTT:
            async def transcribe(self, audio: bytes) -> Any:
                from jarvis.contracts import VoiceTranscript
                return VoiceTranscript("turn on the office light", True)

        class DummyTTS:
            async def synthesize(self, text: str) -> bytes:
                return b"RIFFdummywave"

        class DummyAgent:
            def __init__(self, repo: Any) -> None:
                self.repository = repo

            async def process_text(self, *args: Any, **kwargs: Any) -> Any:
                from jarvis.agents.runtime.runtime import AgentRunOutcome, AgentRunState
                return AgentRunOutcome(
                    run_id="run-voice-001",
                    conversation_id="conv-1",
                    session_id=str(kwargs.get("session_id") or "session-voice-123"),
                    state=AgentRunState.SUCCEEDED,
                    response="Turned on the office light",
                )

        self.voice_core = VoiceCore(DummyAgent(self.repo), self.bus, stt=DummySTT(), tts=DummyTTS())
        self.room_voice = RoomVoiceFabric(
            self.voice_core,
            self.voice_routing,
            self.repo,
            self.bus,
            rooms=self.rooms,
        )

        self.home_transport = InMemoryHomeTransport((
            HomeEntity("light.office", "Office Light", "light", "off", {}, "office"),
            HomeEntity("switch.water_heater", "Water Heater", "switch", "off", {}, "basement"),
            HomeEntity("climate.hvac", "HVAC Thermostat", "climate", "off", {"temperature": 20}, "living_room"),
        ))
        self.mqtt = RestrictedMQTTTransport(allowed_prefixes=(f"jarvis/{self.owner_id}/", "home/"))
        self.home = HomeActionService(
            self.home_transport,
            self.repo,
            self.bus,
            self.permission,
            self.audit,
            mqtt=self.mqtt,
            approval=self.approval,
        )

        # Build mock runtime object for CoreApplication
        class MockRuntime:
            pass

        self.runtime = MockRuntime()
        self.runtime.repository = self.repo
        self.runtime.event_bus = self.bus
        self.runtime.approval = self.approval
        self.runtime.device_fabric = self.fabric
        self.runtime.satellite_transport = self.satellite_transport
        self.runtime.voice_routing = self.voice_routing
        self.runtime.rooms = self.rooms
        self.runtime.room_voice = self.room_voice
        self.runtime.venom = self.venom
        self.runtime.home = self.home
        self.runtime.world_state = self.world_state
        from jarvis.authority.identity.service import IdentityService
        self.identity_service = IdentityService(self.repo, self.bus)
        self.runtime.identity = self.identity_service
        self.runtime.mcp = type("MockMCP", (), {"health_snapshot": lambda: {}, "health_report": lambda: {}})()
        self.runtime.config = type("MockConfig", (), {"heartbeat_interval_seconds": 15})()

        # Wire revocation subscriber
        async def propagate_device_revocation(event: Any) -> None:
            device_id = event.payload.get("device_id")
            owner_id = event.payload.get("owner_id")
            if not isinstance(device_id, str) or not isinstance(owner_id, str):
                return
            await self.satellite_transport.revoke(device_id)
            await self.voice_routing.revoke_device_endpoints(owner_id, device_id)
            await self.world_state.set_fact(
                owner_id,
                f"device.{device_id}.online",
                False,
                source="satellite",
                source_reference=event.event_id,
                freshness_seconds=45,
                device_id=device_id,
            )

        self.bus.subscribe("device.revoked", propagate_device_revocation)

        # Wire device in repo
        self.repo.create_device(
            self.owner_id,
            "Primary PC",
            "primary_pc",
            "windows",
            capabilities=("home.read", "home.control", "voice.input", "voice.output"),
            scopes=("tool.request",),
            device_id=self.device.device_id,
        )

        self.app = CoreApplication(self.runtime)
        await self.rooms.initialize_defaults(self.owner_id)
        self.node_server = CoreNodeHttpServer(self.app, host="127.0.0.1", port=0)
        self.node_server.start()
        self.node_server.wait_ready()
        self.base_url = f"http://127.0.0.1:{self.node_server.port}"

    async def asyncTearDown(self):
        self.node_server.stop()

    # 1. Private LAN Core URL and IP Validation --------------------------
    def test_private_core_url_validation_rfc1918(self):
        # Valid RFC1918 IPv4 in live-distributed mode
        self.assertEqual(validate_private_core_url("http://192.168.1.50:8788", mode="live-distributed"), "http://192.168.1.50:8788")
        self.assertEqual(validate_private_core_url("http://10.0.0.10:8080", mode="live-distributed"), "http://10.0.0.10:8080")
        self.assertEqual(validate_private_core_url("http://172.16.0.5:8788", mode="live-distributed"), "http://172.16.0.5:8788")

        # Valid private hostnames (mock resolver)
        mock_resolver = lambda host: ["192.168.1.100"]
        self.assertEqual(validate_private_core_url("http://nightfury.local:8788", mode="live-distributed", resolver=mock_resolver), "http://nightfury.local:8788")
        self.assertEqual(validate_private_core_url("http://jarvis-core.lan:8788", mode="live-distributed", resolver=mock_resolver), "http://jarvis-core.lan:8788")

    def test_private_core_url_validation_rejections(self):
        # Public IPs rejected in live-distributed mode
        with self.assertRaises(NetworkValidationError):
            validate_private_core_url("http://8.8.8.8:8788", mode="live-distributed")
        with self.assertRaises(NetworkValidationError):
            validate_private_core_url("http://1.1.1.1:8788", mode="live-distributed")

        # Loopback rejected in live-distributed mode
        with self.assertRaises(NetworkValidationError):
            validate_private_core_url("http://127.0.0.1:8788", mode="live-distributed")
        with self.assertRaises(NetworkValidationError):
            validate_private_core_url("http://localhost:8788", mode="live-distributed")

        # Loopback accepted in local/test mode
        self.assertEqual(validate_private_core_url("http://127.0.0.1:8788", mode="local"), "http://127.0.0.1:8788")
        self.assertEqual(validate_private_core_url("http://localhost:8788", mode="test"), "http://localhost:8788")

        # URL credentials/userinfo rejected
        with self.assertRaises(NetworkValidationError):
            validate_private_core_url("http://user:pass@192.168.1.50:8788", mode="live-distributed")

        # Query strings and fragments rejected
        with self.assertRaises(NetworkValidationError):
            validate_private_core_url("http://192.168.1.50:8788?admin=true", mode="live-distributed")
        with self.assertRaises(NetworkValidationError):
            validate_private_core_url("http://192.168.1.50:8788#section", mode="live-distributed")

    def test_is_private_ip(self):
        self.assertTrue(is_private_ip("127.0.0.1"))
        self.assertTrue(is_private_ip("192.168.1.100"))
        self.assertTrue(is_private_ip("10.0.5.1"))
        self.assertTrue(is_private_ip("172.20.0.1"))
        self.assertFalse(is_private_ip("8.8.8.8"))
        self.assertFalse(is_private_ip("93.184.216.34"))

    # 2. Registration != Online Without Live Evidence -------------------
    async def test_enrollment_starts_registered_not_online(self):
        ticket = await self.fabric.issue_enrollment_ticket(
            owner_id=self.owner_id,
            name="Enrolled Living Room Satellite",
            capabilities=("voice.input", "voice.output"),
        )
        req = DeviceEnrollmentRequest(
            code=ticket.code,
            device_id="sat-living-room",
            name="Enrolled Living Room Satellite",
            platform="windows",
        )
        res = await self.fabric.enroll_device(req)
        self.assertTrue(res.accepted)
        self.assertEqual(res.device_id, "sat-living-room")
        self.assertIsNotNone(res.credential)

        # Device status must be REGISTERED, NOT ONLINE
        dev = await self.fabric.get(self.owner_id, "sat-living-room")
        self.assertIsNotNone(dev)
        self.assertEqual(dev.status, DeviceStatus.REGISTERED.value)

        # Only after connect / heartbeat does it transition to ONLINE
        hb_record = await self.fabric.heartbeat(
            DeviceHeartbeat("sat-living-room", datetime.now(UTC)),
            self.owner_id,
        )
        self.assertEqual(hb_record.status, DeviceStatus.ONLINE.value)

    # 3. Canonical Idempotent Device Revocation (No Event Storms) ------
    async def test_device_revocation_idempotent_no_event_storms(self):
        ticket = await self.fabric.issue_enrollment_ticket(
            owner_id=self.owner_id,
            name="Device To Revoke",
        )
        enroll_res = await self.fabric.enroll_device(DeviceEnrollmentRequest(
            code=ticket.code,
            device_id="dev-to-revoke",
            name="Device To Revoke",
            platform="windows",
        ))
        self.assertTrue(enroll_res.accepted)

        revocation_events: list[Any] = []
        self.bus.subscribe("device.revoked", lambda e: revocation_events.append(e))

        # First revocation
        revoked1 = await self.fabric.revoke(self.owner_id, "dev-to-revoke")
        self.assertEqual(revoked1.status, DeviceStatus.REVOKED.value)
        self.assertEqual(len(revocation_events), 1)

        # Second revocation (idempotent - must not re-emit or fail)
        revoked2 = await self.fabric.revoke(self.owner_id, "dev-to-revoke")
        self.assertEqual(revoked2.status, DeviceStatus.REVOKED.value)
        # Still exactly 1 event emitted
        self.assertEqual(len(revocation_events), 1)

        # Wrong owner fails closed
        other_owner = self.repo.create_owner("Other Owner")
        with self.assertRaises(KeyError):
            await self.fabric.revoke(other_owner, "dev-to-revoke")

        # Bus had zero handler errors
        self.assertEqual(self.bus.handler_errors, ())

    # 4. Consequential Home Approvals Integration ----------------------
    async def test_home_action_consequential_approval_workflow(self):
        # Extreme temperature (>30C) triggers consequential approval
        res = await self.home.execute(
            HomeAction("climate.hvac", "set_temperature", {"temperature": 35}, dry_run=False),
            self.identity,
            self.device,
        )
        self.assertEqual(res.status, "approval_required")
        self.assertIsNotNone(res.approval_id)

        # Preview is sanitized and contains no secret tokens
        approval_row = self.repo.approval(res.approval_id)
        self.assertIsNotNone(approval_row)
        preview = json.loads(approval_row["preview_json"])
        self.assertEqual(preview["parameters"]["temperature"], 35)
        self.assertNotIn("credential", preview)

        # Rejecting approval does NOT change state
        rej_res = await self.home.decide_approval(res.approval_id, False, self.identity.identity_id)
        self.assertEqual(rej_res.status, "denied")
        self.assertEqual(self.home_transport.entities["climate.hvac"].attributes["temperature"], 20)

        # Request another consequential action
        res2 = await self.home.execute(
            HomeAction("climate.hvac", "set_temperature", {"temperature": 32}, dry_run=False),
            self.identity,
            self.device,
        )
        self.assertEqual(res2.status, "approval_required")

        # Approving executes exactly once
        app_res = await self.home.decide_approval(res2.approval_id, True, self.identity.identity_id)
        self.assertEqual(app_res.status, "succeeded")
        self.assertEqual(self.home_transport.entities["climate.hvac"].attributes["temperature"], 32)

        # Second decide call on same approval fails safely
        second_decide = await self.home.decide_approval(res2.approval_id, True, self.identity.identity_id)
        self.assertEqual(second_decide.status, "failed")
        self.assertEqual(second_decide.error_code, "pending_action_unavailable_after_restart")

    # 5. Truthful MQTT Delivery & Configuration -------------------------
    async def test_mqtt_truthful_delivery_when_not_configured(self):
        # Unconfigured MQTT transport has configured == False
        unconfigured_mqtt = RestrictedMQTTTransport(publisher=None)
        self.assertFalse(unconfigured_mqtt.configured)

        # Forbidden topics still rejected
        self.assertFalse(await unconfigured_mqtt.publish("evil/topic", "payload"))

        # HomeActionService with unconfigured MQTT fails truthfully
        home_svc = HomeActionService(
            self.home_transport,
            self.repo,
            self.bus,
            self.permission,
            self.audit,
            mqtt=unconfigured_mqtt,
        )
        res = await home_svc.execute(
            HomeAction("mqtt.generic", "publish_mqtt", {"topic": "home/lights", "payload": "1"}, dry_run=False),
            self.identity,
            self.device,
        )
        self.assertEqual(res.status, "failed")
        self.assertEqual(res.error_code, "mqtt_not_configured")
        self.assertFalse(res.verified)

        # Configured MQTT publisher returning True succeeds with verified=True
        configured_mqtt = RestrictedMQTTTransport(publisher=lambda t, p: True)
        self.assertTrue(configured_mqtt.configured)
        home_svc.mqtt = configured_mqtt
        res_ok = await home_svc.execute(
            HomeAction("mqtt.generic", "publish_mqtt", {"topic": "home/lights", "payload": "1"}, dry_run=False),
            self.identity,
            self.device,
        )
        self.assertEqual(res_ok.status, "succeeded")
        self.assertTrue(res_ok.verified)

    # 6. Satellite Remote Command Execution Deadline -------------------
    async def test_satellite_command_execution_deadline(self):
        config = SatelliteAgentConfig(
            core_url="http://127.0.0.1:8788",
            owner_id=self.owner_id,
            identity_id=self.identity.identity_id,
            device_id=self.device.device_id,
            capabilities=frozenset({"computer.observe"}),
        )
        agent = WindowsSatelliteAgent(config, "dummy_cred", network_mode="test")

        # Expired command must be rejected immediately without side effects
        past_deadline = datetime.now(UTC) - timedelta(seconds=10)
        expired_cmd = SatelliteCommand(
            command_id="cmd-expired-1",
            action="inspect_file",
            capability="computer.observe",
            parameters={"operation": "inspect_file", "path": "C:\\test.txt"},
            dry_run=True,
            expires_at=past_deadline,
        )
        observation = await agent.execute_command(expired_cmd)
        self.assertEqual(observation.status, "failed")
        self.assertEqual(observation.error_code, "command_expired")

    # 7. Authenticated Node HTTP Transport Boundary --------------------
    def test_node_http_server_bounded_routes(self):
        # 1. Non-node routes (e.g. /memory, /browser, /chat) return 404
        req = Request(f"{self.base_url}/memory", headers={"Content-Type": "application/json"})
        with self.assertRaises(HTTPError) as ctx:
            urlopen(req)
        self.assertEqual(ctx.exception.code, 404)

        req_browser = Request(f"{self.base_url}/browser/actions", data=b"{}", headers={"Content-Type": "application/json"}, method="POST")
        with self.assertRaises(HTTPError) as ctx:
            urlopen(req_browser)
        self.assertEqual(ctx.exception.code, 404)

        # 2. Detailed node health requires authentication.
        req_health = Request(f"{self.base_url}/venom/health")
        with self.assertRaises(HTTPError) as ctx:
            urlopen(req_health)
        self.assertEqual(ctx.exception.code, 401)

        # 3. Enrollment redemption route works
        ticket_res = asyncio.run(self.fabric.issue_enrollment_ticket(
            owner_id=self.owner_id,
            name="HTTP Node Satellite",
            capabilities=("voice.input", "voice.output"),
        ))
        enroll_body = json.dumps({
            "code": ticket_res.code,
            "device_id": "sat-http-node",
            "name": "HTTP Node Satellite",
            "platform": "windows",
        }).encode("utf-8")
        req_enroll = Request(f"{self.base_url}/nodes/enrollment/redeem", data=enroll_body, headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(req_enroll) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data["accepted"])
            self.assertEqual(data["device_id"], "sat-http-node")
            cred = data["credential"]

        # 4. Authenticated Room Voice endpoint registration
        endpoint_body = json.dumps({
            "endpoint_id": "endpoint-office-speaker",
            "room_id": "office",
            "online": True,
            "input_enabled": True,
            "output_enabled": True,
        }).encode("utf-8")
        auth_headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cred}",
            "X-JARVIS-Device-ID": "sat-http-node",
            "X-JARVIS-Identity-ID": self.identity.identity_id,
        }
        req_ep = Request(f"{self.base_url}/nodes/rooms/register_endpoint", data=endpoint_body, headers=auth_headers, method="POST")
        with urlopen(req_ep) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["endpoint_id"], "endpoint-office-speaker")
            self.assertEqual(data["device_id"], "sat-http-node")

        # 5. Room voice utterance from registered endpoint
        utt_body = json.dumps({
            "session_id": "session-voice-123",
            "endpoint_id": "endpoint-office-speaker",
            "room_id": "office",
            "text": "turn on the office light",
        }).encode("utf-8")
        req_utt = Request(f"{self.base_url}/nodes/voice/utterance", data=utt_body, headers=auth_headers, method="POST")
        try:
            with urlopen(req_utt) as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(data["session_id"], "session-voice-123")
                self.assertIn("text", data)
        except HTTPError as exc:
            print("REQ_UTT ERROR:", exc.read().decode("utf-8"))
            raise

        # 6. Attempted utterance with mismatched device_id fails closed
        spoof_headers = dict(auth_headers)
        spoof_headers["X-JARVIS-Device-ID"] = "dev-primary"  # Different device trying to spoof endpoint
        req_spoof = Request(f"{self.base_url}/nodes/voice/utterance", data=utt_body, headers=spoof_headers, method="POST")
        with self.assertRaises(HTTPError) as ctx:
            urlopen(req_spoof)
        self.assertIn(ctx.exception.code, (401, 403, 500))

    def test_authenticated_satellite_get_poll_and_command_delivery(self):
        # 1. Enroll satellite device
        ticket_res = asyncio.run(self.fabric.issue_enrollment_ticket(
            owner_id=self.owner_id,
            name="Poll Satellite",
            capabilities=("computer.observe", "perception.screen"),
        ))
        enroll_res = asyncio.run(self.fabric.enroll_device(DeviceEnrollmentRequest(
            code=ticket_res.code,
            device_id="sat-poll-device",
            name="Poll Satellite",
            platform="windows",
        )))
        self.assertTrue(enroll_res.accepted)
        cred = enroll_res.credential

        auth_headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cred}",
            "X-JARVIS-Device-ID": "sat-poll-device",
            "X-JARVIS-Identity-ID": self.identity.identity_id,
        }

        # 2. Connect satellite via POST /nodes/satellite/connect
        connect_body = json.dumps({
            "capabilities": ["computer.observe", "perception.screen"],
            "platform": "windows",
            "software_version": "1.0.0",
            "protocol_version": "2",
        }).encode("utf-8")
        req_conn = Request(f"{self.base_url}/nodes/satellite/connect", data=connect_body, headers=auth_headers, method="POST")
        with urlopen(req_conn) as resp:
            self.assertEqual(resp.status, 200)
            conn_data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(conn_data["accepted"])
            session_id = conn_data["session_id"]

        # 3. Authenticated GET poll when idle -> returns {"command": None}
        req_poll_idle = Request(f"{self.base_url}/nodes/satellite/commands?session_id={session_id}&wait_seconds=0", headers=auth_headers, method="GET")
        with urlopen(req_poll_idle) as resp:
            self.assertEqual(resp.status, 200)
            idle_data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("command", idle_data)
            self.assertIsNone(idle_data["command"])

        # 4. Enqueue a pending command for the connected satellite
        from jarvis.devices.satellite.transport import _PendingCommand, _fingerprint
        cmd = SatelliteCommand(
            command_id="cmd-poll-123",
            action="perception",
            capability="perception.screen",
            parameters={"operation": "observe_screen"},
            dry_run=False,
            protocol_version="2",
        )
        session = self.satellite_transport._sessions[session_id]
        fingerprint = _fingerprint(cmd)
        pending = _PendingCommand(cmd, fingerprint, datetime.now(UTC) + timedelta(seconds=30))
        session.pending[cmd.command_id] = pending
        session.commands.put_nowait(cmd)

        # 5. Authenticated GET poll delivers the queued command
        req_poll_cmd = Request(f"{self.base_url}/nodes/satellite/commands?session_id={session_id}&wait_seconds=1.0", headers=auth_headers, method="GET")
        with urlopen(req_poll_cmd) as resp:
            self.assertEqual(resp.status, 200)
            cmd_data = json.loads(resp.read().decode("utf-8"))
            self.assertIsNotNone(cmd_data.get("command"))
            self.assertEqual(cmd_data["command"]["command_id"], "cmd-poll-123")
            self.assertEqual(cmd_data["command"]["action"], "perception")
            self.assertEqual(cmd_data["command"]["capability"], "perception.screen")

        # 6. Bad credentials are rejected (401)
        bad_auth_headers = dict(auth_headers, Authorization="Bearer invalid-cred-xyz")
        req_bad_cred = Request(f"{self.base_url}/nodes/satellite/commands?session_id={session_id}&wait_seconds=0", headers=bad_auth_headers, method="GET")
        with self.assertRaises(HTTPError) as ctx:
            urlopen(req_bad_cred)
        self.assertEqual(ctx.exception.code, 401)

        # 7. Mismatched device is rejected (401)
        bad_dev_headers = dict(auth_headers, **{"X-JARVIS-Device-ID": "sat-wrong-device"})
        req_bad_dev = Request(f"{self.base_url}/nodes/satellite/commands?session_id={session_id}&wait_seconds=0", headers=bad_dev_headers, method="GET")
        with self.assertRaises(HTTPError) as ctx:
            urlopen(req_bad_dev)
        self.assertEqual(ctx.exception.code, 401)

    # 8. Venom Node Daemon Runtime & Telemetry -------------------------
    def test_venom_daemon_runtime_and_heartbeat(self):
        # Create enrolled Venom device credentials
        ticket_res = asyncio.run(self.fabric.issue_enrollment_ticket(
            owner_id=self.owner_id,
            name="Venom Server",
            role=DeviceRole.SERVER.value,
            capabilities=("node.health",),
        ))
        enroll_res = asyncio.run(self.fabric.enroll_device(DeviceEnrollmentRequest(
            code=ticket_res.code,
            device_id="venom-node-01",
            name="Venom Server",
            platform="linux",
        )))
        self.assertTrue(enroll_res.accepted)

        # Write test config file
        temp_config = {
            "node_id": "venom-node-01",
            "device_id": "venom-node-01",
            "identity_id": self.identity.identity_id,
            "credential": enroll_res.credential,
            "core_url": f"http://127.0.0.1:{self.node_server.port}",
            "mqtt_enabled": True,
        }
        config_path = self.db._path if hasattr(self.db, "_path") else None

        daemon = VenomDaemon(mode="test")
        daemon._config = temp_config
        self.assertEqual(daemon.device_id, "venom-node-01")
        self.assertEqual(daemon.core_url, f"http://127.0.0.1:{self.node_server.port}")

        # Send heartbeat to Core node transport
        ok = daemon.send_heartbeat()
        self.assertTrue(ok)
        self.assertTrue(daemon.node.health().available)
        self.assertEqual(daemon.node.health().reason, "heartbeat_acknowledged")

        # Telemetry truth: Mosquitto is marked degraded if mqtt_enabled is True but port is closed
        services = daemon.collect_services()
        mosq = next(s for s in services if s["name"] == "mosquitto")
        # Since no broker is listening on 1883 in this unit test process, it must truthfully report degraded
        self.assertEqual(mosq["status"], "degraded")
        self.assertFalse(mosq["active"])

        # Capability truth: unimplemented/unconfigured capabilities report not_configured
        caps = daemon.collect_capabilities()
        self.assertEqual(caps["mqtt_broker"], "degraded")
        self.assertEqual(caps["backup_receiver"], "not_configured")
        self.assertEqual(caps["event_relay"], "not_configured")
        self.assertEqual(caps["ha_bridge"], "not_configured")

        # Core projection truth: Core's VenomNode detailed health reflects submitted telemetry
        core_health = self.app.venom_detailed_health()
        self.assertTrue(core_health["available"])
        self.assertEqual(core_health["status"], "online")
        self.assertIsNotNone(core_health["storage"])
        self.assertIn(core_health["storage"]["status"], {"healthy", "warning", "critical"})
        self.assertGreaterEqual(core_health["storage"]["total_bytes"], 0)
        self.assertTrue(any(s["service_name"] == "mosquitto" and not s["active"] for s in core_health["services"]))
        self.assertEqual(core_health["capabilities"]["mqtt_broker"], "degraded")
        self.assertEqual(core_health["capabilities"]["backup_receiver"], "not_configured")

        # Verify device fabric recorded heartbeat for Venom device
        venom_dev = asyncio.run(self.fabric.get(self.owner_id, "venom-node-01"))
        self.assertIsNotNone(venom_dev)
        self.assertEqual(venom_dev.status, "online")

        # Bounded telemetry: arbitrary and secret fields in heartbeat request are not reflected in projected telemetry
        principal = DemoPrincipal(identity=self.identity, device=DeviceIdentity("venom-node-01", "Venom", "server", frozenset({"node.host"})))
        res_hb = asyncio.run(self.app.venom_heartbeat(principal, {
            "healthy": True,
            "details": "custom_heartbeat",
            "secret_token": "super_secret_token_12345",
            "injected_arbitrary_key": "dangerous_value",
            "storage": {"total_bytes": 10000, "free_bytes": 8000, "used_bytes": 2000},
            "services": [{"name": "mosquitto", "active": True, "status": "running"}],
            "capabilities": {"mqtt_broker": "running"},
        }))
        self.assertTrue(res_hb["healthy"])
        bounded_core_health = self.app.venom_detailed_health()
        self.assertNotIn("secret_token", bounded_core_health)
        self.assertNotIn("injected_arbitrary_key", bounded_core_health)
        self.assertEqual(bounded_core_health["capabilities"]["mqtt_broker"], "running")
        self.assertEqual(bounded_core_health["storage"]["total_bytes"], 10000)

    def test_venom_provisioning_idempotent_and_safe_dry_run(self):
        import tempfile
        from pathlib import Path
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "venom"))
        import setup as venom_setup

        # Dry-run execution
        dry_res = venom_setup.provision(dry_run=True)
        self.assertEqual(dry_res["status"], "dry_run")
        self.assertIn("plan_systemd_unit", dry_res["steps_completed"])

        # Safe mock execution in temporary directory
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            install_dir = tmp_path / "opt" / "jarvis-venom"
            config_dir = tmp_path / "etc" / "jarvis"
            data_dir = tmp_path / "var" / "lib" / "jarvis" / "backups"
            log_dir = tmp_path / "var" / "log" / "jarvis"
            systemd_dir = tmp_path / "etc" / "systemd" / "system"

            executed_commands: list[list[str]] = []
            def mock_runner(cmd: list[str]) -> tuple[int, str]:
                executed_commands.append(cmd)
                return 0, "ok"

            res = venom_setup.provision(
                install_dir=install_dir,
                config_dir=config_dir,
                data_dir=data_dir,
                log_dir=log_dir,
                systemd_dir=systemd_dir,
                user="jarvis-test",
                group="jarvis-test",
                dry_run=False,
                start_service=True,
                command_runner=mock_runner,
            )
            self.assertEqual(res["status"], "success")
            self.assertTrue((config_dir / "venom.json").is_file())
            self.assertTrue((config_dir / "venom.env").is_file())
            self.assertTrue((systemd_dir / "jarvis-venom.service").is_file())
            self.assertIn("systemctl_enable", res["steps_completed"])
            self.assertIn("systemctl_start", res["steps_completed"])
            self.assertIn(str(config_dir / "venom.json"), res["rollback_metadata"]["created_files"])

    def test_main_cli_node_server_wiring(self):
        import argparse
        import jarvis.__main__ as jmain

        # Create parser and test args
        parser = argparse.ArgumentParser()
        parser.add_argument("--serve-node", action="store_true")
        parser.add_argument("--node-host", default="127.0.0.1")
        parser.add_argument("--node-port", type=int, default=8788)
        parser.add_argument("--allow-wildcard-node-bind", action="store_true")

        parsed = parser.parse_args(["--serve-node", "--node-host", "192.168.1.50", "--node-port", "8888"])
        self.assertTrue(parsed.serve_node)
        self.assertEqual(parsed.node_host, "192.168.1.50")
        self.assertEqual(parsed.node_port, 8888)
        self.assertFalse(parsed.allow_wildcard_node_bind)

    def test_node_http_server_bind_host_safety_and_wildcard_opt_in(self):
        # Default server binds safely to loopback
        default_server = CoreNodeHttpServer(self.app, host="127.0.0.1", port=0)
        self.assertEqual(default_server.host, "127.0.0.1")

        # Wildcard without explicit opt-in is rejected
        with self.assertRaises(ValueError) as ctx:
            CoreNodeHttpServer(self.app, host="0.0.0.0", port=0, allow_wildcard_bind=False)
        self.assertIn("wildcard_bind_requires_explicit_opt_in", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            CoreNodeHttpServer(self.app, host="::", port=0, allow_wildcard_bind=False)
        self.assertIn("wildcard_bind_requires_explicit_opt_in", str(ctx.exception))

        # Wildcard with explicit opt-in is permitted
        opted_in = CoreNodeHttpServer(self.app, host="0.0.0.0", port=0, allow_wildcard_bind=True)
        self.assertEqual(opted_in.host, "0.0.0.0")

        # Public IP bind is rejected
        with self.assertRaises(ValueError) as ctx:
            CoreNodeHttpServer(self.app, host="8.8.8.8", port=0)
        self.assertIn("public_or_invalid_bind_host", str(ctx.exception))

    def test_private_core_url_safe_dns_proof_resolution(self):
        # Mock resolver resolving to private RFC1918
        def private_resolver(host: str) -> list[str]:
            if host == "core.local":
                return ["192.168.1.150"]
            raise ValueError("not_found")

        validated = validate_private_core_url("http://core.local:8788", mode="live-distributed", resolver=private_resolver)
        self.assertEqual(validated, "http://core.local:8788")

        # Mock resolver resolving to public IP in live-distributed mode is rejected
        def public_resolver(host: str) -> list[str]:
            if host == "evil.internal":
                return ["142.250.180.14"]
            raise ValueError("not_found")

        with self.assertRaises(NetworkValidationError) as ctx:
            validate_private_core_url("http://evil.internal:8788", mode="live-distributed", resolver=public_resolver)
        self.assertIn("hostname_resolves_to_public_ip", str(ctx.exception))

        # Mock resolver resolving to loopback in live-distributed mode is rejected
        def loopback_resolver(host: str) -> list[str]:
            return ["127.0.0.1"]

        with self.assertRaises(NetworkValidationError) as ctx:
            validate_private_core_url("http://core.local:8788", mode="live-distributed", resolver=loopback_resolver)
        self.assertIn("hostname_resolves_to_loopback_in_live_distributed_mode", str(ctx.exception))

    def test_room_voice_registration_and_lan_barge_in_device_binding(self):
        # 1. Registration with nonexistent room fails closed and leaves zero state in voice routing / personalization
        from jarvis.contracts import DeviceIdentity, Identity
        principal = DemoPrincipal(
            identity=self.identity,
            device=self.device,
        )
        with self.assertRaises(KeyError):
            asyncio.run(self.app.register_room_voice_endpoint(principal, {
                "endpoint_id": "ep-invalid-room",
                "room_id": "nonexistent-room-999",
            }))

        # Verify no endpoint was left in VoiceRoutingService memory or repository personalization
        self.assertNotIn("ep-invalid-room", self.voice_routing._endpoints)
        pers_keys = [r.get("key") for r in self.repo.personalization(self.owner_id)]
        self.assertNotIn("voice_endpoint:ep-invalid-room", pers_keys)

        # 2. Register valid endpoint in real room
        asyncio.run(self.rooms.create_room(self.owner_id, "Kitchen", room_id="kitchen"))
        ep_res = asyncio.run(self.app.register_room_voice_endpoint(principal, {
            "endpoint_id": "ep-kitchen-mic",
            "room_id": "kitchen",
        }))
        self.assertEqual(ep_res["endpoint_id"], "ep-kitchen-mic")

        # 3. LAN barge-in with matching device succeeds
        barge_res = asyncio.run(self.app.room_voice_barge_in({
            "session_id": "sess-test-barge",
            "endpoint_id": "ep-kitchen-mic",
        }, principal=principal))
        self.assertTrue(barge_res["barge_in"])

        # 4. LAN barge-in with different device fails closed
        different_device = DeviceIdentity("dev-satellite-other", "Other Satellite", "desktop", frozenset({"voice.input"}))
        diff_principal = DemoPrincipal(identity=self.identity, device=different_device)
        barge_diff = asyncio.run(self.app.room_voice_barge_in({
            "session_id": "sess-test-barge",
            "endpoint_id": "ep-kitchen-mic",
        }, principal=diff_principal))
        self.assertFalse(barge_diff["barge_in"])

    def test_venom_daemon_bounded_reconnect_backoff_and_recovery(self):
        slept: list[float] = []
        daemon = VenomDaemon(
            mode="test",
            sleeper=lambda d: slept.append(d),
        )
        daemon._config = {
            "node_id": "venom-node-01",
            "device_id": "venom-node-01",
            "identity_id": self.identity.identity_id,
            "credential": "test_cred",
            "core_url": f"http://127.0.0.1:{self.node_server.port}",
            "mqtt_enabled": False,
        }

        # Test calculate_next_delay exponential progression and cap
        daemon.consecutive_failures = 0
        self.assertEqual(daemon.calculate_next_delay(base_interval=10.0, max_interval=60.0), 10.0)
        daemon.consecutive_failures = 1
        self.assertEqual(daemon.calculate_next_delay(base_interval=10.0, max_interval=60.0), 10.0)
        daemon.consecutive_failures = 2
        self.assertEqual(daemon.calculate_next_delay(base_interval=10.0, max_interval=60.0), 20.0)
        daemon.consecutive_failures = 3
        self.assertEqual(daemon.calculate_next_delay(base_interval=10.0, max_interval=60.0), 40.0)
        daemon.consecutive_failures = 4
        self.assertEqual(daemon.calculate_next_delay(base_interval=10.0, max_interval=60.0), 60.0)
        daemon.consecutive_failures = 5
        self.assertEqual(daemon.calculate_next_delay(base_interval=10.0, max_interval=60.0), 60.0)

        # Mock opener: 2 failures followed by 1 success
        attempts = 0
        def mock_opener(req: Any, timeout: float = 5.0) -> Any:
            nonlocal attempts
            attempts += 1
            if attempts <= 2:
                raise TimeoutError("connection_timeout")
            class MockResp:
                status = 200
                def __enter__(self): return self
                def __exit__(self, *args): pass
            return MockResp()

        daemon.opener = mock_opener
        daemon.consecutive_failures = 0

        # Run 3 bounded iterations
        ret = daemon.run(poll_interval=10.0, max_interval=60.0, max_iterations=3)
        self.assertEqual(ret, 0)
        self.assertEqual(attempts, 3)
        # Verify backing off slept durations: attempt 1 failed -> delay 10, attempt 2 failed -> delay 20
        self.assertEqual(slept, [10.0, 20.0])
        # After 3rd attempt succeeded: health is recovered and failures reset to 0
        self.assertEqual(daemon.consecutive_failures, 0)
        self.assertTrue(daemon.node.health().available)
        self.assertEqual(daemon.node.health().reason, "heartbeat_acknowledged")

        # Test clean shutdown during execution
        slept.clear()
        def stopping_sleeper(d: float) -> None:
            slept.append(d)
            daemon.stop()

        daemon.sleeper = stopping_sleeper
        ret_stopped = daemon.run(poll_interval=10.0, max_iterations=5)
        self.assertEqual(ret_stopped, 0)
        self.assertEqual(len(slept), 1)
        self.assertFalse(daemon.node.health().available)
        self.assertEqual(daemon.node.health().reason, "daemon_stopped")

    def test_esp32_command_id_required_no_random_uuid(self):
        mqtt = RestrictedMQTTTransport(allowed_prefixes=(f"jarvis/{self.owner_id}/",))

        # Missing command_id -> must be rejected (returns None)
        bad_payload = json.dumps({"action": "set_level", "parameters": {"level": 50}})
        bad_env = mqtt.parse_esp32_command(f"jarvis/{self.owner_id}/dev-esp/command/led", bad_payload)
        self.assertIsNone(bad_env)

        # Empty command_id -> rejected
        empty_id_payload = json.dumps({"command_id": "  ", "action": "set_level"})
        empty_env = mqtt.parse_esp32_command(f"jarvis/{self.owner_id}/dev-esp/command/led", empty_id_payload)
        self.assertIsNone(empty_env)

        # Valid command_id -> accepted
        valid_payload = json.dumps({"command_id": "cmd-explicit-123", "action": "set_level"})
        valid_env = mqtt.parse_esp32_command(f"jarvis/{self.owner_id}/dev-esp/command/led", valid_payload)
        self.assertIsNotNone(valid_env)
        self.assertEqual(valid_env.command_id, "cmd-explicit-123")

    def test_home_approval_owner_scoping_and_denial_zero_execution(self):
        home_action = HomeAction("climate.hvac", "set_temperature", {"temperature": 10})
        res = asyncio.run(self.home.execute(home_action, self.identity, self.device))
        self.assertEqual(res.status, "approval_required")
        approval_id = res.approval_id

        # Wrong owner trying to decide approval -> denied
        wrong_owner_res = asyncio.run(self.home.decide_approval(approval_id, True, "wrong-owner-id"))
        self.assertEqual(wrong_owner_res.status, "denied")
        self.assertEqual(wrong_owner_res.error_code, "approval_owner_mismatch")

        # Proper owner denies approval -> denied, zero transport executions
        denied_res = asyncio.run(self.home.decide_approval(approval_id, False, self.owner_id))
        self.assertEqual(denied_res.status, "denied")
        self.assertEqual(denied_res.error_code, "approval_rejected")


if __name__ == "__main__":
    unittest.main()
