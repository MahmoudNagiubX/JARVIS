"""Product-owned on-demand perception service."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from ..authority.audit.service import DurableAuditService
from ..authority.permissions.engine import PolicyPermissionEngine
from ..bus import InMemoryEventBus
from ..contracts import AuditRecord, DeviceIdentity, Identity, PermissionEffect, PerceptionResult, PerceptionProvider, ScreenObservation, VisualRegion
from ..events import Event, EventCategory, EventState
from ..persistence.repositories import RuntimeRepository
from .providers import DeferredPerceptionProvider


class PerceptionService:
    """Capture only on request; raw frames never enter the repository."""

    def __init__(self, repository: RuntimeRepository, event_bus: InMemoryEventBus, permission: PolicyPermissionEngine, audit: DurableAuditService, provider: PerceptionProvider | None = None, ocr: object | None = None) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.permission = permission
        self.audit = audit
        self.provider = provider or DeferredPerceptionProvider()
        self.ocr = ocr
        self._capture_count = 0
        self._error_count = 0

    def capabilities(self) -> dict[str, object]:
        return {"screen_capture": bool(self.provider.available), "ocr": bool(getattr(self.ocr, "available", False)), "local_vision": False, "camera": False, "continuous_capture": False, "raw_frame_retention": False, "provider": self.provider.name}

    async def capture_screen(self, identity: Identity, device: DeviceIdentity, *, window: str | None = None, region: VisualRegion | None = None) -> PerceptionResult:
        decision = await self.permission.evaluate(identity, device, "perception.screen.capture", {"required_scope": "tool.request", "required_capabilities": ("computer.observe",), "risk_level": "read"})
        if decision.effect is PermissionEffect.DENY:
            return PerceptionResult("denied", error_code=decision.reason_code)
        correlation = f"perception-{uuid4()}"
        await self._emit("perception.capture.started", identity, device, {"owner_id": identity.owner_id, "device_id": device.device_id, "correlation_id": correlation})
        try:
            observation = await self.provider.capture(device.device_id, window, region)
            # Copy the metadata-only observation to force the retention invariant.
            observation = ScreenObservation(observation.observation_id, observation.device_id, observation.captured_at, observation.source, observation.width, observation.height, observation.active_window, observation.text, observation.elements, observation.region, False, observation.confidence, dict(observation.metadata))
            self._capture_count += 1
            await self._emit("perception.capture.completed", identity, device, {"owner_id": identity.owner_id, "device_id": device.device_id, "observation_id": observation.observation_id}, EventState.COMPLETED)
            if self.ocr is not None and getattr(self.ocr, "available", False):
                observation = await self.ocr.extract(observation)
                await self._emit("perception.ocr.completed", identity, device, {"owner_id": identity.owner_id, "device_id": device.device_id, "observation_id": observation.observation_id}, EventState.COMPLETED)
            await self.audit.record(AuditRecord(f"audit-{uuid4()}", "perception.capture.completed", datetime.now(UTC), identity.identity_id, device.device_id, correlation, "completed", None, {"provider": self.provider.name, "raw_retained": False}))
            return PerceptionResult("completed", observation)
        except Exception as exc:
            self._error_count += 1
            await self._emit("perception.capture.failed", identity, device, {"owner_id": identity.owner_id, "device_id": device.device_id, "error_code": exc.args[0] if exc.args and isinstance(exc.args[0], str) else exc.__class__.__name__}, EventState.FAILED)
            return PerceptionResult("deferred" if not self.provider.available else "failed", error_code=exc.args[0] if exc.args and isinstance(exc.args[0], str) else exc.__class__.__name__)

    async def capture_window(self, identity: Identity, device: DeviceIdentity, window: str) -> PerceptionResult:
        if not window.strip() or len(window) > 300:
            raise ValueError("window must be bounded")
        return await self.capture_screen(identity, device, window=window)

    async def _emit(self, event_type: str, identity: Identity, device: DeviceIdentity, payload: dict[str, object], state: EventState = EventState.EMITTED) -> None:
        event = Event.create(event_type, EventCategory.PERCEPTION, correlation_id=str(payload.get("correlation_id", payload.get("observation_id", uuid4()))), actor_id=identity.identity_id, payload=payload, state=state)
        self.repository.append_event(event)
        await self.event_bus.publish(event)
