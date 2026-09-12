"""Local Home Assistant/MQTT boundaries with explicit action allowlists."""

from __future__ import annotations

import asyncio
import inspect
import json
import re
import urllib.error
import urllib.request
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from ...authority.approvals.service import DurableApprovalEngine
from ...authority.audit.service import DurableAuditService
from ...authority.permissions.engine import PolicyPermissionEngine
from ...bus import InMemoryEventBus
from ...network.validation import validate_private_core_url
from ...contracts import (
    ApprovalRequest,
    ApprovalStatus,
    AuditRecord,
    DeviceIdentity,
    ESP32Ack,
    ESP32CommandEnvelope,
    ESP32DeviceManifest,
    ESP32StateEnvelope,
    HomeAction,
    HomeEntity,
    HomeEntityMapping,
    HomeResult,
    HomeTransport,
    Identity,
    MQTTTransport,
    ToolContext,
)
from ...events import Event, EventCategory, EventState
from ...persistence.repositories import RuntimeRepository


class InMemoryHomeTransport:
    """Deterministic local transport for tests and offline development."""

    name = "in-memory-home"

    def __init__(self, entities: tuple[HomeEntity, ...] = ()) -> None:
        self.entities: dict[str, HomeEntity] = {item.entity_id: item for item in entities}

    async def list_entities(self) -> tuple[HomeEntity, ...]:
        return tuple(self.entities.values())

    async def execute(self, action: HomeAction) -> HomeResult:
        entity = self.entities.get(action.entity_id)
        if entity is None:
            return HomeResult("failed", error_code="home_entity_not_found")
        if action.dry_run:
            return HomeResult("succeeded", {"dry_run": True, "entity_id": action.entity_id, "action": action.action}, verified=True)
        if action.action in {"turn_on", "turn_off"}:
            new_state = "on" if action.action == "turn_on" else "off"
            self.entities[action.entity_id] = HomeEntity(entity.entity_id, entity.name, entity.domain, new_state, entity.attributes, entity.room_id, datetime.now(UTC))
            return HomeResult("succeeded", {"state": new_state, "entity_id": action.entity_id}, verified=True)
        if action.action == "set_temperature":
            temp = action.parameters.get("temperature")
            if not isinstance(temp, (int, float)):
                return HomeResult("denied", error_code="temperature_invalid")
            attributes = dict(entity.attributes)
            attributes["temperature"] = temp
            self.entities[action.entity_id] = HomeEntity(entity.entity_id, entity.name, entity.domain, entity.state, attributes, entity.room_id, datetime.now(UTC))
            return HomeResult("succeeded", {"temperature": temp, "entity_id": action.entity_id}, verified=True)
        if action.action == "set_brightness":
            brightness = action.parameters.get("brightness")
            if not isinstance(brightness, (int, float)) or not 0 <= brightness <= 100:
                return HomeResult("denied", error_code="brightness_invalid")
            attributes = dict(entity.attributes)
            attributes["brightness"] = brightness
            self.entities[action.entity_id] = HomeEntity(entity.entity_id, entity.name, entity.domain, entity.state, attributes, entity.room_id, datetime.now(UTC))
            return HomeResult("succeeded", {"brightness": brightness, "entity_id": action.entity_id}, verified=True)
        if action.action == "set_color":
            color = action.parameters.get("color")
            if not isinstance(color, str) or not color.strip():
                return HomeResult("denied", error_code="color_invalid")
            attributes = dict(entity.attributes)
            attributes["color"] = color.strip()
            self.entities[action.entity_id] = HomeEntity(entity.entity_id, entity.name, entity.domain, entity.state, attributes, entity.room_id, datetime.now(UTC))
            return HomeResult("succeeded", {"color": color.strip(), "entity_id": action.entity_id}, verified=True)
        if action.action == "trigger_scene":
            return HomeResult("succeeded", {"scene": action.entity_id}, verified=True)
        return HomeResult("denied", error_code="home_action_not_allowed")


class HomeAssistantTransport:
    """Outbound Home Assistant REST bridge."""

    name = "home-assistant"

    def __init__(self, base_url: str = "http://127.0.0.1:8123", token: str | None = None, request: Callable[..., tuple[int, bytes]] | None = None) -> None:
        self.base_url = validate_private_core_url(base_url, mode="local")
        self._token = token
        self._request = request

    async def list_entities(self) -> tuple[HomeEntity, ...]:
        status, body = await asyncio.to_thread(self._call, "GET", "/api/states", None)
        if status != 200:
            raise RuntimeError(f"home_assistant_http_{status}")
        decoded = json.loads(body.decode("utf-8"))
        if not isinstance(decoded, list):
            raise RuntimeError("home_assistant_invalid_states")
        result = []
        for item in decoded[:500]:
            if not isinstance(item, dict) or not isinstance(item.get("entity_id"), str):
                continue
            entity_id = item["entity_id"]
            attributes = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
            result.append(HomeEntity(entity_id, str(attributes.get("friendly_name", entity_id)), entity_id.split(".", 1)[0], str(item.get("state", "unknown")), attributes, attributes.get("room_id"), datetime.fromisoformat(item["last_updated"]) if isinstance(item.get("last_updated"), str) else None))
        return tuple(result)

    async def execute(self, action: HomeAction) -> HomeResult:
        service_map = {"turn_on": "turn_on", "turn_off": "turn_off", "set_brightness": "turn_on", "set_color": "turn_on", "trigger_scene": "turn_on", "set_temperature": "set_temperature"}
        if action.action not in service_map:
            return HomeResult("denied", error_code="home_action_not_allowed")
        if action.dry_run:
            return HomeResult("succeeded", {"dry_run": True, "entity_id": action.entity_id, "action": action.action}, verified=True)
        domain = action.entity_id.split(".", 1)[0]
        service = service_map[action.action]
        data = {"entity_id": action.entity_id, **dict(action.parameters)}
        if action.action == "set_brightness":
            brightness = data.get("brightness")
            if not isinstance(brightness, (int, float)) or not 0 <= brightness <= 100:
                return HomeResult("denied", error_code="brightness_invalid")
            data["brightness_pct"] = brightness
            data.pop("brightness", None)
        if action.action == "set_temperature" and not isinstance(data.get("temperature"), (int, float)):
            return HomeResult("denied", error_code="temperature_invalid")
        try:
            status, _ = await asyncio.to_thread(self._call, "POST", f"/api/services/{domain}/{service}", json.dumps(data).encode("utf-8"))
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            # Provider disconnect/timeout must degrade truthfully, not escape as an
            # uncaught exception from the canonical Home action path.
            return HomeResult("failed", {"entity_id": action.entity_id}, f"home_assistant_unreachable:{exc.__class__.__name__}", False)
        if not 200 <= status < 300:
            return HomeResult("failed", {"http_status": status, "entity_id": action.entity_id}, f"home_assistant_http_{status}", False)
        # HTTP acceptance is not physical proof. Verification requires an
        # independent, bounded (single-attempt, no polling) state read-back.
        verified = await self._verify_state(action, data)
        return HomeResult("succeeded", {"http_status": status, "entity_id": action.entity_id}, None, verified)

    async def _verify_state(self, action: HomeAction, data: Mapping[str, object]) -> bool:
        if action.action not in {"turn_on", "turn_off", "set_brightness", "set_temperature"}:
            # set_color/trigger_scene have no deterministic, generically comparable
            # state on the standard entity endpoint - report honestly, never guess.
            return False
        try:
            status, body = await asyncio.to_thread(self._call, "GET", f"/api/states/{action.entity_id}", None)
        except (urllib.error.URLError, OSError, TimeoutError):
            return False
        if status != 200:
            return False
        try:
            decoded = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return False
        if not isinstance(decoded, dict):
            return False
        state = decoded.get("state")
        attributes = decoded.get("attributes") if isinstance(decoded.get("attributes"), dict) else {}
        if action.action == "turn_on":
            return state == "on"
        if action.action == "turn_off":
            return state == "off"
        if action.action == "set_brightness":
            return attributes.get("brightness_pct") == data.get("brightness_pct")
        if action.action == "set_temperature":
            return attributes.get("temperature") == data.get("temperature")
        return False

    def _call(self, method: str, path: str, body: bytes | None) -> tuple[int, bytes]:
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        if self._request:
            return self._request(method, self.base_url + path, body, headers)
        request = urllib.request.Request(self.base_url + path, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, response.read(2_000_000)
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read(100_000)


class RestrictedMQTTTransport:
    """MQTT seam that permits only configured topic prefixes and validated ESP32 messages."""

    name = "mqtt"

    def __init__(
        self,
        publisher: Callable[[str, str], bool | Awaitable[bool]] | None = None,
        allowed_prefixes: tuple[str, ...] = ("jarvis/", "home/"),
    ) -> None:
        self._publisher = publisher
        self.allowed_prefixes = tuple(prefix for prefix in allowed_prefixes if prefix)
        self.published: list[tuple[str, str]] = []

    @property
    def configured(self) -> bool:
        return self._publisher is not None

    async def publish(self, topic: str, payload: str, *, retain: bool = False) -> bool:
        if not topic or not any(topic.startswith(prefix) for prefix in self.allowed_prefixes):
            return False
        if len(topic) > 250 or len(payload) > 10000:
            return False
        # Do not allow retained dangerous commands
        if retain and "/command/" in topic:
            return False
        if self._publisher is None:
            return False
        result = self._publisher(topic, payload)
        success = bool(await result if inspect.isawaitable(result) else result)
        if success:
            self.published.append((topic, payload))
        return success

    async def subscribe(self, topic: str) -> bool:
        return bool(topic and any(topic.startswith(prefix) for prefix in self.allowed_prefixes))

    def parse_esp32_state(self, topic: str, payload: str) -> ESP32StateEnvelope | None:
        """Parse inbound ESP32 telemetry from a state topic."""
        try:
            if not any(topic.startswith(prefix) for prefix in self.allowed_prefixes):
                return None
            parts = topic.split("/")
            # Topic format: jarvis/<owner>/<device>/state/<target>
            if len(parts) < 5 or parts[3] != "state":
                return None
            device_id = parts[2]
            target = "/".join(parts[4:])
            data = json.loads(payload)
            if not isinstance(data, dict):
                return None
            return ESP32StateEnvelope(
                device_id=device_id,
                target=target,
                state=data,
                timestamp=datetime.now(UTC),
                online=bool(data.get("online", True)),
            )
        except (ValueError, TypeError, KeyError):
            return None

    def parse_esp32_command(self, topic: str, payload: str) -> ESP32CommandEnvelope | None:
        """Parse inbound command payload, validating TTL, command_id, and schema."""
        try:
            if not any(topic.startswith(prefix) for prefix in self.allowed_prefixes):
                return None
            parts = topic.split("/")
            if len(parts) < 5 or parts[3] != "command":
                return None
            device_id = parts[2]
            target = parts[4]
            if not target or not re.match(r"^[A-Za-z0-9_.-]{1,64}$", target):
                return None
            data = json.loads(payload)
            if not isinstance(data, dict):
                return None
            command_id = str(data.get("command_id", "")).strip()
            if not command_id or len(command_id) > 128:
                return None
            action = str(data.get("action", target)).strip()
            if not action or len(action) > 64:
                return None
            params = data.get("parameters") if isinstance(data.get("parameters"), dict) else {}
            now = datetime.now(UTC)
            if "expires_at" in data and isinstance(data["expires_at"], str):
                try:
                    exp_dt = datetime.fromisoformat(data["expires_at"])
                    expires_at = exp_dt if exp_dt.tzinfo else exp_dt.replace(tzinfo=UTC)
                except Exception:
                    return None
            else:
                ttl = int(data.get("ttl_seconds", 30))
                if ttl <= 0 or ttl > 300:
                    return None
                expires_at = now + timedelta(seconds=ttl)
            if expires_at <= now:
                return None
            return ESP32CommandEnvelope(
                command_id=command_id,
                device_id=device_id,
                target=target,
                action=action,
                parameters=params,
                expires_at=expires_at,
                dry_run=bool(data.get("dry_run", False)),
            )
        except (ValueError, TypeError, KeyError):
            return None

    def format_esp32_ack(self, ack: ESP32Ack) -> tuple[str, str]:
        topic = f"jarvis/ack/{ack.device_id}/{ack.command_id}"
        payload = json.dumps({"command_id": ack.command_id, "status": ack.status, "output": ack.output, "error": ack.error, "timestamp": ack.timestamp.isoformat()})
        return topic, payload


class HomeActionService:
    """Safe model-callable Home Assistant tool boundary with capability-checked allowlists."""

    _safe_actions = frozenset({"turn_on", "turn_off", "set_brightness", "set_color", "trigger_scene", "set_temperature", "publish_mqtt"})
    _read_actions = frozenset({"get_state", "list_entities", "read_sensor", "read_state"})
    _blocked_actions = frozenset({"lock", "unlock", "alarm", "security_override", "life_safety_override", "raw_shell", "system_exec"})

    def __init__(
        self,
        transport: HomeTransport | None,
        repository: RuntimeRepository,
        event_bus: InMemoryEventBus,
        permission: PolicyPermissionEngine,
        audit: DurableAuditService,
        mqtt: MQTTTransport | None = None,
        approval: DurableApprovalEngine | None = None,
    ) -> None:
        self.transport = transport
        self.repository = repository
        self.event_bus = event_bus
        self.permission = permission
        self.audit = audit
        self.mqtt = mqtt
        self.approval = approval
        self._entity_mappings: dict[str, HomeEntityMapping] = {}
        self._explicitly_configured: bool = False
        self._pending_approvals: dict[str, tuple[HomeAction, Identity, DeviceIdentity, str]] = {}
        self._ensure_in_memory_mappings()

    def _ensure_in_memory_mappings(self) -> None:
        if self._explicitly_configured:
            return
        if isinstance(self.transport, InMemoryHomeTransport):
            for e in self.transport.entities.values():
                if e.entity_id not in self._entity_mappings:
                    self._entity_mappings[e.entity_id] = HomeEntityMapping(
                        entity_id=e.entity_id,
                        display_name=e.name,
                        domain=e.domain,
                        room_id=e.room_id,
                        read_caps=frozenset({"home.read"}),
                        write_caps=frozenset({"home.control"}),
                        risk_level="safe",
                        enabled=True,
                    )

    def register_entity_mapping(self, mapping: HomeEntityMapping) -> None:
        self._explicitly_configured = True
        self._entity_mappings[mapping.entity_id] = mapping

    def get_entity_mapping(self, entity_id: str) -> HomeEntityMapping | None:
        self._ensure_in_memory_mappings()
        return self._entity_mappings.get(entity_id)

    def list_entity_mappings(self) -> tuple[HomeEntityMapping, ...]:
        self._ensure_in_memory_mappings()
        return tuple(self._entity_mappings.values())

    async def list_entities(self, identity: Identity, device: DeviceIdentity) -> tuple[HomeEntity, ...]:
        if self.transport is None:
            return ()
        decision = await self.permission.evaluate(identity, device, "home.read", {"required_scope": "tool.request", "required_capabilities": frozenset({"home.read"}), "risk_level": "read"})
        if decision.effect.value != "allow":
            return ()
        self._ensure_in_memory_mappings()
        provider_entities = {e.entity_id: e for e in await self.transport.list_entities()}
        result = []
        for mapping in self._entity_mappings.values():
            if not mapping.enabled:
                continue
            provider_e = provider_entities.get(mapping.entity_id)
            if provider_e is not None:
                result.append(
                    HomeEntity(
                        mapping.entity_id,
                        mapping.display_name or provider_e.name,
                        mapping.domain or provider_e.domain,
                        provider_e.state,
                        provider_e.attributes,
                        mapping.room_id or provider_e.room_id,
                        provider_e.updated_at,
                    )
                )
            else:
                result.append(
                    HomeEntity(
                        mapping.entity_id,
                        mapping.display_name or mapping.entity_id,
                        mapping.domain,
                        "unknown",
                        {},
                        mapping.room_id,
                        None,
                    )
                )
        return tuple(result)

    async def execute(self, action: HomeAction, identity: Identity, device: DeviceIdentity, *, session_id: str = "home", correlation_id: str | None = None) -> HomeResult:
        correlation = correlation_id or f"home-{uuid4()}"
        if action.action in self._blocked_actions:
            return await self._denied(identity, device, correlation, action, "home_action_blocked")
        if action.action not in self._safe_actions and action.action not in self._read_actions:
            return await self._denied(identity, device, correlation, action, "home_action_not_allowed")

        self._ensure_in_memory_mappings()

        # Enforce enabled HomeEntityMapping for model-callable entity actions
        mapping = None
        if action.action != "publish_mqtt":
            mapping = self._entity_mappings.get(action.entity_id)
            if mapping is None:
                return await self._denied(identity, device, correlation, action, "home_entity_unknown")
            if not mapping.enabled:
                return await self._denied(identity, device, correlation, action, "home_entity_disabled")

            if action.action in self._read_actions:
                required_caps = mapping.read_caps or frozenset({"home.read"})
                risk_level = mapping.risk_level or "read"
            else:
                required_caps = mapping.write_caps or frozenset({"home.control"})
                risk_level = mapping.risk_level or "safe"
        else:
            required_caps = frozenset({"home.control"})
            risk_level = "safe"

        extreme_temp = False
        # Consequential check for temperature extremes
        if action.action == "set_temperature":
            temp = action.parameters.get("temperature")
            if isinstance(temp, (int, float)) and (temp < 15 or temp > 30):
                risk_level = "consequential"
                extreme_temp = True

        decision = await self.permission.evaluate(
            identity,
            device,
            f"home.{action.action}",
            {
                "required_scope": "tool.request",
                "required_capabilities": required_caps,
                "risk_level": risk_level,
            },
        )
        if decision.effect.value != "allow":
            if decision.effect.value == "require_approval" and self.approval is not None:
                approval_id = f"approval-home-{uuid4()}"
                now = datetime.now(UTC)
                expires_at = now + timedelta(minutes=15)
                # Build sanitized preview: NO tokens, NO passwords, NO internal secrets
                preview = {
                    "entity_id": action.entity_id,
                    "action": action.action,
                    "domain": mapping.domain if mapping else (action.entity_id.split(".", 1)[0] if "." in action.entity_id else "home"),
                    "parameters": {k: v for k, v in action.parameters.items() if k in {"temperature", "brightness", "color", "state", "scene"}},
                    "risk_level": risk_level,
                }
                reason = "extreme_temperature_requires_approval" if extreme_temp else (decision.reason_code or "approval_required")
                req = ApprovalRequest(
                    approval_id=approval_id,
                    action=f"home.{action.action}",
                    requester_id=identity.owner_id,
                    device_id=device.device_id,
                    reason=reason,
                    created_at=now,
                    expires_at=expires_at,
                    preview=preview,
                )
                await self.approval.request(req)
                self._pending_approvals[approval_id] = (action, identity, device, correlation)
                await self._emit("home.approval_requested", identity.owner_id, correlation, {"approval_id": approval_id, "entity_id": action.entity_id, "action": action.action}, EventState.ACCEPTED)
                return HomeResult(
                    status="approval_required",
                    output={"approval_id": approval_id, "entity_id": action.entity_id, "action": action.action},
                    error_code=reason,
                    verified=False,
                    approval_id=approval_id,
                )
            status = "approval_required" if decision.effect.value == "require_approval" else "denied"
            reason = "extreme_temperature_requires_approval" if (extreme_temp and status == "approval_required") else decision.reason_code
            return await self._denied(identity, device, correlation, action, reason, status)
        await self._emit("home.action_started", identity.owner_id, correlation, {"entity_id": action.entity_id, "action": action.action}, EventState.ACCEPTED)
        if action.action == "publish_mqtt":
            if self.mqtt is None or not getattr(self.mqtt, "configured", True):
                return await self._denied(identity, device, correlation, action, "mqtt_not_configured", status="failed")
            topic = action.parameters.get("topic")
            payload = action.parameters.get("payload", "")
            if not isinstance(topic, str) or not isinstance(payload, str) or not await self.mqtt.publish(topic, payload):
                return HomeResult("failed", error_code="mqtt_publish_failed")
            result = HomeResult("succeeded", {"topic": topic}, verified=True)
        elif self.transport is None:
            result = HomeResult("failed", error_code="home_service_unavailable")
        elif action.action in self._read_actions:
            entity = next((item for item in await self.transport.list_entities() if item.entity_id == action.entity_id), None)
            result = HomeResult(
                "succeeded",
                {"entity": action.entity_id, "state": entity.state, "attributes": dict(entity.attributes)} if entity else {},
                None if entity else "home_entity_not_found",
                entity is not None,
            )
        else:
            result = await self.transport.execute(action)
        event_type = "home.action_completed" if result.status == "succeeded" else "home.action_failed"
        if result.status == "succeeded":
            await self._emit("home.state_updated", identity.owner_id, correlation, {"entity_id": action.entity_id, "action": action.action}, EventState.COMPLETED)
        await self._emit(event_type, identity.owner_id, correlation, {"entity_id": action.entity_id, "action": action.action, "error_code": result.error_code}, EventState.COMPLETED if result.status == "succeeded" else EventState.FAILED)
        await self.audit.record(AuditRecord(f"audit-{uuid4()}", event_type, datetime.now(UTC), identity.identity_id, device.device_id, correlation, result.status, result.error_code, {"entity_id": action.entity_id, "action": action.action}))
        return result

    async def decide_approval(self, approval_id: str, approved: bool, decided_by: str) -> HomeResult:
        """Exactly-once resume decision for a pending consequential home action."""
        if self.approval is None:
            return HomeResult("failed", error_code="approval_engine_unavailable")
        app_row = self.repository.approval(approval_id)
        if app_row is None:
            return HomeResult("failed", error_code="approval_request_not_found")

        pending = self._pending_approvals.get(approval_id)
        if pending is None:
            return HomeResult("failed", {"approval_id": approval_id}, error_code="pending_action_unavailable_after_restart", verified=False, approval_id=approval_id)

        req_id = app_row.get("requester_id")
        decider_owner = decided_by
        if hasattr(self.repository, "identity"):
            id_rec = self.repository.identity(decided_by)
            if id_rec:
                decider_owner = id_rec.get("owner_id", decided_by)
        valid_decider = (
            decided_by in ("owner", req_id, pending[1].identity_id, pending[1].owner_id)
            or decider_owner in ("owner", req_id)
        )
        if not valid_decider:
            return HomeResult("denied", error_code="approval_owner_mismatch")

        decide_with_claim = getattr(self.approval, "decide_with_claim", None)
        if callable(decide_with_claim):
            decision, claimed = await decide_with_claim(approval_id, approved, decided_by)
        else:
            decision = await self.approval.decide(approval_id, approved, decided_by)
            claimed = decision.status == ApprovalStatus.APPROVED and app_row.get("status") == ApprovalStatus.PENDING.value
        if not claimed:
            self._pending_approvals.pop(approval_id, None)
            return HomeResult(
                "failed",
                {"approval_id": approval_id},
                error_code="approval_already_decided",
                verified=False,
                approval_id=approval_id,
            )
        self._pending_approvals.pop(approval_id, None)

        if not approved or decision.status != ApprovalStatus.APPROVED:
            action, identity, device, correlation = pending
            await self._emit("home.approval_rejected", identity.owner_id, correlation, {"approval_id": approval_id, "action": action.action}, EventState.COMPLETED)
            return HomeResult("denied", {"approval_id": approval_id}, error_code="approval_rejected", verified=False, approval_id=approval_id)

        action, identity, device, correlation = pending
        if action.action == "publish_mqtt":
            if self.mqtt is None or not getattr(self.mqtt, "configured", True):
                return await self._denied(identity, device, correlation, action, "mqtt_not_configured", status="failed")
            topic = action.parameters.get("topic")
            payload = action.parameters.get("payload", "")
            if not isinstance(topic, str) or not isinstance(payload, str) or not await self.mqtt.publish(topic, payload):
                return HomeResult("failed", error_code="mqtt_publish_failed")
            result = HomeResult("succeeded", {"topic": topic}, verified=True)
        elif self.transport is None:
            result = HomeResult("failed", error_code="home_service_unavailable")
        else:
            result = await self.transport.execute(action)

        event_type = "home.action_completed" if result.status == "succeeded" else "home.action_failed"
        if result.status == "succeeded":
            await self._emit("home.state_updated", identity.owner_id, correlation, {"entity_id": action.entity_id, "action": action.action}, EventState.COMPLETED)
        await self._emit(event_type, identity.owner_id, correlation, {"entity_id": action.entity_id, "action": action.action, "error_code": result.error_code}, EventState.COMPLETED if result.status == "succeeded" else EventState.FAILED)
        await self.audit.record(AuditRecord(f"audit-{uuid4()}", event_type, datetime.now(UTC), identity.identity_id, device.device_id, correlation, result.status, result.error_code, {"entity_id": action.entity_id, "action": action.action}))
        return result

    async def _emit(self, event_type: str, owner_id: str, correlation: str, payload: dict[str, object], state: EventState) -> None:
        event = Event.create(event_type, EventCategory.HOME, correlation_id=correlation, actor_id=owner_id, payload=payload, state=state)
        self.repository.append_event(event)
        await self.event_bus.publish(event)

    async def _denied(self, identity: Identity, device: DeviceIdentity, correlation: str, action: HomeAction, error_code: str, status: str = "denied") -> HomeResult:
        await self._emit("home.action_failed", identity.owner_id, correlation, {"entity_id": action.entity_id, "action": action.action, "error_code": error_code}, EventState.FAILED)
        await self.audit.record(AuditRecord(f"audit-{uuid4()}", "home.action_failed", datetime.now(UTC), identity.identity_id, device.device_id, correlation, status, error_code, {"entity_id": action.entity_id, "action": action.action}))
        return HomeResult(status, error_code=error_code)
