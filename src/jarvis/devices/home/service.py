"""Local Home Assistant/MQTT boundaries with explicit action allowlists."""

from __future__ import annotations

import asyncio
import inspect
import json
import urllib.error
import urllib.request
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from uuid import uuid4

from ...authority.audit.service import DurableAuditService
from ...authority.permissions.engine import PolicyPermissionEngine
from ...bus import InMemoryEventBus
from ...contracts import (
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
        attributes = dict(entity.attributes)
        state = entity.state
        if action.action == "turn_on":
            state = "on"
        elif action.action == "turn_off":
            state = "off"
        elif action.action in {"read_state", "read_sensor"}:
            return HomeResult("succeeded", {"entity": entity.entity_id, "state": entity.state, "attributes": dict(entity.attributes)}, verified=True)
        elif action.action == "set_brightness":
            brightness = action.parameters.get("brightness")
            if not isinstance(brightness, (int, float)) or not 0 <= brightness <= 100:
                return HomeResult("denied", error_code="brightness_invalid")
            attributes["brightness"] = brightness
        elif action.action == "set_color":
            color = action.parameters.get("color")
            if not isinstance(color, str) or not color.strip():
                return HomeResult("denied", error_code="color_invalid")
            attributes["color"] = color.strip()
        elif action.action in {"trigger_scene", "set_temperature", "publish_mqtt"}:
            attributes["last_action"] = action.action
            attributes.update(action.parameters)
        else:
            return HomeResult("denied", error_code="home_action_not_allowed")
        self.entities[action.entity_id] = HomeEntity(entity.entity_id, entity.name, entity.domain, state, attributes, entity.room_id, datetime.now(UTC))
        return HomeResult("succeeded", {"entity": action.entity_id, "state": state, "attributes": attributes}, verified=True)


class HomeAssistantTransport:
    """HTTP adapter for an already-running local Home Assistant instance."""

    name = "home-assistant"

    def __init__(self, base_url: str, token: str | None = None, request: Callable[[str, str, bytes | None, Mapping[str, str]], tuple[int, bytes]] | None = None) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("home assistant URL must be HTTP")
        self.base_url = base_url.rstrip("/")
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
        status, _ = await asyncio.to_thread(self._call, "POST", f"/api/services/{domain}/{service}", json.dumps(data).encode("utf-8"))
        return HomeResult("succeeded" if 200 <= status < 300 else "failed", {"http_status": status, "entity_id": action.entity_id}, None if 200 <= status < 300 else f"home_assistant_http_{status}", 200 <= status < 300)

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

    async def publish(self, topic: str, payload: str, *, retain: bool = False) -> bool:
        if not topic or not any(topic.startswith(prefix) for prefix in self.allowed_prefixes):
            return False
        if len(topic) > 250 or len(payload) > 10000:
            return False
        # Do not allow retained dangerous commands
        if retain and "/command/" in topic:
            return False
        self.published.append((topic, payload))
        if self._publisher is None:
            return True
        result = self._publisher(topic, payload)
        return bool(await result if inspect.isawaitable(result) else result)

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
        """Parse inbound command payload, validating TTL and schema."""
        try:
            if not any(topic.startswith(prefix) for prefix in self.allowed_prefixes):
                return None
            parts = topic.split("/")
            # Topic format: jarvis/<owner>/<device>/command/<target>
            if len(parts) < 5 or parts[3] != "command":
                return None
            device_id = parts[2]
            target = "/".join(parts[4:])
            data = json.loads(payload)
            if not isinstance(data, dict):
                return None
            command_id = str(data.get("command_id", ""))
            action = str(data.get("action", ""))
            if not command_id or not action:
                return None
            expires_at = None
            if data.get("expires_at"):
                expires_at = datetime.fromisoformat(str(data["expires_at"]))
                if expires_at <= datetime.now(UTC):
                    # Stale command expired
                    return None
            return ESP32CommandEnvelope(
                command_id=command_id,
                device_id=device_id,
                target=target,
                action=action,
                parameters=data.get("parameters", {}) if isinstance(data.get("parameters"), dict) else {},
                expires_at=expires_at,
                dry_run=bool(data.get("dry_run", False)),
            )
        except (ValueError, TypeError, KeyError):
            return None


class HomeActionService:
    """Home action authority with explicit read/safe/high-risk boundaries."""

    _read_actions = frozenset({"list_entities", "read_state", "read_sensor"})
    _safe_actions = frozenset({"turn_on", "turn_off", "set_brightness", "set_color", "trigger_scene", "set_temperature", "publish_mqtt"})
    _blocked_actions = frozenset({"lock", "unlock", "alarm", "security_override", "life_safety_override", "raw_shell", "system_exec"})

    def __init__(
        self,
        transport: HomeTransport | None,
        repository: RuntimeRepository,
        event_bus: InMemoryEventBus,
        permission: PolicyPermissionEngine,
        audit: DurableAuditService,
        mqtt: MQTTTransport | None = None,
    ) -> None:
        self.transport = transport
        self.repository = repository
        self.event_bus = event_bus
        self.permission = permission
        self.audit = audit
        self.mqtt = mqtt
        self._entity_mappings: dict[str, HomeEntityMapping] = {}
        self._explicitly_configured: bool = False
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
            status = "approval_required" if decision.effect.value == "require_approval" else "denied"
            reason = "extreme_temperature_requires_approval" if (extreme_temp and status == "approval_required") else decision.reason_code
            return await self._denied(identity, device, correlation, action, reason, status)
        await self._emit("home.action_started", identity.owner_id, correlation, {"entity_id": action.entity_id, "action": action.action}, EventState.ACCEPTED)
        if action.action == "publish_mqtt":
            if self.mqtt is None:
                return HomeResult("failed", error_code="mqtt_not_configured")
            topic = action.parameters.get("topic")
            payload = action.parameters.get("payload", "")
            if not isinstance(topic, str) or not isinstance(payload, str) or not await self.mqtt.publish(topic, payload):
                return HomeResult("denied", error_code="mqtt_topic_not_allowed")
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

    async def _emit(self, event_type: str, owner_id: str, correlation: str, payload: dict[str, object], state: EventState) -> None:
        event = Event.create(event_type, EventCategory.HOME, correlation_id=correlation, actor_id=owner_id, payload=payload, state=state)
        self.repository.append_event(event)
        await self.event_bus.publish(event)

    async def _denied(self, identity: Identity, device: DeviceIdentity, correlation: str, action: HomeAction, error_code: str, status: str = "denied") -> HomeResult:
        await self._emit("home.action_failed", identity.owner_id, correlation, {"entity_id": action.entity_id, "action": action.action, "error_code": error_code}, EventState.FAILED)
        await self.audit.record(AuditRecord(f"audit-{uuid4()}", "home.action_failed", datetime.now(UTC), identity.identity_id, device.device_id, correlation, status, error_code, {"entity_id": action.entity_id, "action": action.action}))
        return HomeResult(status, error_code=error_code)
