"""Canonical on-demand perception service with privacy and ephemeral retention."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Awaitable, Callable
from uuid import uuid4

from ..authority.audit.service import DurableAuditService
from ..authority.permissions.engine import PolicyPermissionEngine
from ..bus import InMemoryEventBus
from ..contracts import (
    AuditRecord,
    DesktopContextSnapshot,
    DeviceIdentity,
    Identity,
    PermissionEffect,
    PerceptionPrivacyMode,
    PerceptionResult,
    PerceptionProvider,
    ScreenObservation,
    VisualRegion,
)
from ..events import Event, EventCategory, EventState
from ..persistence.repositories import RuntimeRepository
from .cache import ObservationCache
from .browser import BrowserDomPerceptionBridge
from .desktop import ActiveDesktopContextService
from .privacy import PerceptionPrivacyPolicy
from .providers import DeferredPerceptionProvider
from .router import DesktopPerceptionRouter


DeviceLookup = Callable[[str, str], Awaitable[object | None]]


class PerceptionService:
    """The only perception authority; pixels exist only during one request."""

    def __init__(
        self,
        repository: RuntimeRepository,
        event_bus: InMemoryEventBus,
        permission: PolicyPermissionEngine,
        audit: DurableAuditService,
        provider: PerceptionProvider | None = None,
        ocr: object | None = None,
        *,
        router: DesktopPerceptionRouter | None = None,
        privacy: PerceptionPrivacyPolicy | None = None,
        cache: ObservationCache | None = None,
        desktop_context: ActiveDesktopContextService | None = None,
        device_lookup: DeviceLookup | None = None,
        browser_dom: BrowserDomPerceptionBridge | None = None,
    ) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.permission = permission
        self.audit = audit
        self.provider = provider or DeferredPerceptionProvider()
        self.ocr = ocr
        self.privacy = privacy or PerceptionPrivacyPolicy()
        self.cache = cache or ObservationCache()
        self.desktop = desktop_context or ActiveDesktopContextService()
        self.device_lookup = device_lookup
        self.router = router
        self.browser_dom = browser_dom
        self._capture_count = 0
        self._error_count = 0
        self._awareness_targets: dict[tuple[str, str], tuple[Identity, DeviceIdentity]] = {}

    def capabilities(self) -> dict[str, object]:
        provider_caps = self.provider.capabilities() if hasattr(self.provider, "capabilities") else {}
        return {
            "screen_capture": bool(getattr(self.provider, "available", False)),
            "metadata": bool(getattr(self.provider, "available", False)),
            "ocr": bool(getattr(self.ocr, "available", False)),
            "local_vision": False,
            "camera": False,
            "continuous_capture": False,
            "metadata_awareness": bool(self._awareness_targets),
            "raw_frame_retention": False,
            "privacy_mode": self.privacy.mode.value,
            "provider": getattr(self.provider, "name", "unknown"),
            **(provider_caps if isinstance(provider_caps, dict) else {}),
        }

    def health(self) -> dict[str, object]:
        return {
            "provider": getattr(self.provider, "name", "unknown"),
            "available": bool(getattr(self.provider, "available", False)),
            "captures": self._capture_count,
            "errors": self._error_count,
            "cached_observations": len(self.cache),
            "privacy_mode": self.privacy.mode.value,
            "raw_frame_retention": False,
            "continuous_capture": False,
        }

    async def observe_desktop_context(
        self,
        identity: Identity,
        device: DeviceIdentity,
        *,
        target_device: DeviceIdentity | None = None,
        session_id: str = "perception",
    ) -> PerceptionResult:
        target = target_device or device
        denied = await self._authorize(identity, device, target, require_pixels=False)
        if denied is not None:
            return denied
        try:
            snapshot = await self._desktop_snapshot(identity, device, target, session_id)
            privacy_reason = self.privacy.check_snapshot(snapshot)
            if privacy_reason:
                await self._safe_denial(identity, device, privacy_reason)
                return PerceptionResult("denied", error_code=privacy_reason)
            await self.desktop.update(identity.owner_id, session_id, snapshot)
            self.cache.put(identity.owner_id, target.device_id, session_id, snapshot, now=snapshot.observed_at)
            return PerceptionResult("completed", context=snapshot)
        except (RuntimeError, ValueError) as exc:
            self._error_count += 1
            return PerceptionResult("failed", error_code=_error_code(exc))

    async def observe_screen(
        self,
        identity: Identity,
        device: DeviceIdentity,
        *,
        target_device: DeviceIdentity | None = None,
        target_device_id: str | None = None,
        window_ref: str | None = None,
        region: VisualRegion | None = None,
        mode: str = "screen",
        session_id: str = "perception",
    ) -> PerceptionResult:
        if mode not in {"semantic", "screen"}:
            return PerceptionResult("denied", error_code="unsupported_perception_mode")
        if window_ref is not None and not isinstance(window_ref, str):
            return PerceptionResult("denied", error_code="window_ref_required")
        target = target_device or device
        if target_device_id is not None and target_device_id != target.device_id:
            return PerceptionResult("denied", error_code="target_device_mismatch")
        denied = await self._authorize(identity, device, target, require_pixels=mode == "screen")
        if denied is not None:
            return denied
        if region is not None:
            validation_error = _validate_public_region(region)
            if validation_error:
                return PerceptionResult("denied", error_code=validation_error)
        if window_ref is not None and not window_ref.startswith("window-"):
            return PerceptionResult("denied", error_code="window_ref_required")
        try:
            context = await self._desktop_snapshot(identity, device, target, session_id)
            privacy_reason = self.privacy.check_snapshot(context)
            if privacy_reason:
                await self._safe_denial(identity, device, privacy_reason)
                return PerceptionResult("denied", error_code=privacy_reason)
            if mode == "screen":
                pixel_reason = self.privacy.check_capture()
                if pixel_reason:
                    await self._safe_denial(identity, device, pixel_reason)
                    return PerceptionResult("denied", error_code=pixel_reason)
            observation = await self._screen_observation(identity, device, target, context, window_ref, region, mode, session_id)
            await self.desktop.update(identity.owner_id, session_id, context)
            self.cache.put(identity.owner_id, target.device_id, session_id, observation, now=observation.captured_at)
            self._capture_count += 1
            return PerceptionResult("completed", observation=observation, context=context)
        except (RuntimeError, ValueError) as exc:
            self._error_count += 1
            return PerceptionResult("failed", error_code=_error_code(exc))

    async def latest_observation(
        self,
        identity: Identity,
        device: DeviceIdentity,
        *,
        observation_id: str | None = None,
        session_id: str = "perception",
    ) -> PerceptionResult:
        denied = await self._authorize(identity, device, device, require_pixels=False)
        if denied is not None:
            return denied
        value = self.cache.get(identity.owner_id, device.device_id, session_id, observation_id, now=datetime.now(UTC)) if observation_id else self.cache.latest(identity.owner_id, device.device_id, session_id)
        if value is None:
            return PerceptionResult("failed", error_code="observation_not_found_or_expired")
        if isinstance(value, DesktopContextSnapshot):
            return PerceptionResult("completed", context=value)
        return PerceptionResult("completed", observation=value)

    async def observe_browser_dom(self, identity: Identity, device: DeviceIdentity, browser_session_id: str, *, session_id: str = "perception") -> PerceptionResult:
        if self.browser_dom is None:
            return PerceptionResult("failed", error_code="browser_dom_unavailable")
        denied = await self._authorize(identity, device, device, require_pixels=False)
        if denied is not None:
            return denied
        try:
            observation = self._metadata_only(await self.browser_dom.observe(identity, device, browser_session_id))
            self.cache.put(identity.owner_id, device.device_id, session_id, observation, now=observation.captured_at)
            return PerceptionResult("completed", observation=observation)
        except (RuntimeError, ValueError) as exc:
            return PerceptionResult("failed", error_code=_error_code(exc))

    async def resolve_target(self, identity: Identity, request_device: DeviceIdentity, target_device_id: object) -> DeviceIdentity | None:
        if target_device_id is None:
            return request_device
        if not isinstance(target_device_id, str):
            return None
        if not target_device_id.strip():
            return request_device
        if self.device_lookup is None:
            return request_device if target_device_id == request_device.device_id else None
        record = await self.device_lookup(identity.owner_id, target_device_id)
        if record is None:
            return None
        return DeviceIdentity(
            str(getattr(record, "device_id", target_device_id)),
            str(getattr(record, "owner_id", identity.owner_id)),
            str(getattr(record, "role", "desktop")),
            "windows",
            frozenset(getattr(record, "capabilities", ())),
            frozenset({"tool.request"}),
        )

    async def capture_screen(
        self,
        identity: Identity,
        device: DeviceIdentity,
        *,
        window: str | None = None,
        region: VisualRegion | None = None,
        session_id: str = "perception",
    ) -> PerceptionResult:
        """Backward-compatible Phase 05 API; still remains on-demand and private."""

        decision = await self.permission.evaluate(
            identity, device, "perception.screen.capture",
            {"required_scope": "tool.request", "required_capabilities": ("computer.observe",), "risk_level": "read"},
        )
        if decision.effect is PermissionEffect.DENY:
            return PerceptionResult("denied", error_code=decision.reason_code)
        if self.privacy.check_capture():
            return PerceptionResult("denied", error_code="privacy_policy_denied")
        correlation = f"perception-{uuid4()}"
        await self._emit("perception.capture.started", identity, device, {"owner_id": identity.owner_id, "device_id": device.device_id, "correlation_id": correlation})
        try:
            observation = await self.provider.capture(device.device_id, window, region)
            observation = self._metadata_only(observation)
            if self.ocr is not None and getattr(self.ocr, "available", False):
                observation = self._metadata_only(await self.ocr.extract(observation))
            self.cache.put(identity.owner_id, device.device_id, session_id, observation, now=observation.captured_at)
            self._capture_count += 1
            await self._emit("perception.capture.completed", identity, device, {"owner_id": identity.owner_id, "device_id": device.device_id, "observation_id": observation.observation_id}, EventState.COMPLETED)
            await self.audit.record(AuditRecord(f"audit-{uuid4()}", "perception.capture.completed", datetime.now(UTC), identity.identity_id, device.device_id, correlation, "completed", None, {"provider": getattr(self.provider, "name", "unknown"), "raw_retained": False}))
            return PerceptionResult("completed", observation=observation)
        except Exception as exc:
            self._error_count += 1
            code = _error_code(exc)
            await self._emit("perception.capture.failed", identity, device, {"owner_id": identity.owner_id, "device_id": device.device_id, "error_code": code}, EventState.FAILED)
            return PerceptionResult("deferred" if not getattr(self.provider, "available", False) else "failed", error_code=code)

    async def capture_window(self, identity: Identity, device: DeviceIdentity, window: str, *, session_id: str = "perception") -> PerceptionResult:
        if not window.strip() or len(window) > 300:
            raise ValueError("window must be bounded")
        return await self.capture_screen(identity, device, window=window, session_id=session_id)

    def clear(self) -> None:
        self.cache.clear()
        self.desktop.clear()

    async def shutdown(self) -> None:
        self.clear()
        self._awareness_targets.clear()

    def enable_metadata_awareness(self, identity: Identity, device: DeviceIdentity) -> None:
        if self.privacy.mode is PerceptionPrivacyMode.OFF:
            raise PermissionError("privacy_policy_denied")
        self._awareness_targets[(identity.owner_id, device.device_id)] = (identity, device)

    def disable_metadata_awareness(self, owner_id: str, device_id: str) -> None:
        self._awareness_targets.pop((owner_id, device_id), None)

    async def poll_metadata_awareness(self) -> int:
        """Optional scheduler callback: metadata only, never a pixel capture."""
        observed = 0
        for identity, device in tuple(self._awareness_targets.values()):
            try:
                result = await self.observe_desktop_context(identity, device, session_id="awareness")
                if result.status == "completed":
                    observed += 1
            except Exception:
                self._error_count += 1
        return observed

    async def _authorize(self, identity: Identity, request_device: DeviceIdentity, target: DeviceIdentity, *, require_pixels: bool) -> PerceptionResult | None:
        if identity.owner_id != request_device.owner_id or identity.owner_id != target.owner_id:
            return PerceptionResult("denied", error_code="target_owner_mismatch")
        if self.privacy.mode is PerceptionPrivacyMode.OFF:
            await self._safe_denial(identity, request_device, "privacy_policy_denied")
            return PerceptionResult("denied", error_code="privacy_policy_denied")
        if self.device_lookup is not None:
            record = await self.device_lookup(identity.owner_id, target.device_id)
            status = getattr(record, "status", None)
            if status in {"revoked", "offline"}:
                return PerceptionResult("denied", error_code="perception_target_revoked" if status == "revoked" else "perception_target_offline")
            if record is None:
                return PerceptionResult("denied", error_code="target_device_missing")
        if "perception.screen" not in target.capabilities:
            return PerceptionResult("denied", error_code="target_capability_missing")
        decision = await self.permission.evaluate(identity, request_device, "perception.screen.observe", {"required_scope": "tool.request", "required_capabilities": (), "risk_level": "read"})
        if decision.effect is PermissionEffect.DENY:
            return PerceptionResult("denied", error_code=decision.reason_code)
        if require_pixels and self.privacy.check_capture():
            await self._safe_denial(identity, request_device, "privacy_policy_denied")
            return PerceptionResult("denied", error_code="privacy_policy_denied")
        return None

    async def _desktop_snapshot(self, identity: Identity, request: DeviceIdentity, target: DeviceIdentity, session_id: str) -> DesktopContextSnapshot:
        if self.router is not None:
            force_satellite = target.device_id != request.device_id
            return await self.router.desktop_context(target, owner_id=identity.owner_id, session_id=session_id, force_satellite=force_satellite)
        context = self.provider.desktop_context(target.device_id) if hasattr(self.provider, "desktop_context") else DesktopContextSnapshot(f"snapshot-{target.device_id}", target.device_id, datetime.now(UTC), source=getattr(self.provider, "name", "local"), confidence=0.0)
        return await context if hasattr(context, "__await__") else context

    async def _screen_observation(self, identity: Identity, request: DeviceIdentity, target: DeviceIdentity, context: DesktopContextSnapshot, window_ref: str | None, region: VisualRegion | None, mode: str, session_id: str) -> ScreenObservation:
        if region is not None and context.display_width and context.display_height:
            if region.x + region.width > context.display_width or region.y + region.height > context.display_height:
                raise ValueError("capture_region_out_of_bounds")
        if self.router is not None:
            return await self.router.screen(target, owner_id=identity.owner_id, session_id=session_id, window_ref=window_ref, region=region, mode=mode, force_satellite=target.device_id != request.device_id)
        result = self.provider.capture(target.device_id, window_ref, region)
        return self._metadata_only(await result if hasattr(result, "__await__") else result)

    @staticmethod
    def _metadata_only(observation: ScreenObservation) -> ScreenObservation:
        text = observation.text[:16_000] if isinstance(observation.text, str) else observation.text
        return ScreenObservation(observation.observation_id, observation.device_id, observation.captured_at, observation.source, observation.width, observation.height, observation.active_window, text, tuple(observation.elements[:200]), observation.region, False, observation.confidence, dict(observation.metadata))

    async def _safe_denial(self, identity: Identity, device: DeviceIdentity, reason: str) -> None:
        await self._emit("perception.privacy_policy_denied", identity, device, {"owner_id": identity.owner_id, "device_id": device.device_id, "reason": reason}, EventState.FAILED)
        await self.audit.record(AuditRecord(f"audit-{uuid4()}", "privacy_policy_denied", datetime.now(UTC), identity.identity_id, device.device_id, f"perception-{device.device_id}", "denied", reason, {"reason": reason}))

    async def _emit(self, event_type: str, identity: Identity, device: DeviceIdentity, payload: dict[str, object], state: EventState = EventState.EMITTED) -> None:
        event = Event.create(event_type, EventCategory.PERCEPTION, correlation_id=str(payload.get("correlation_id", payload.get("observation_id", uuid4()))), actor_id=identity.identity_id, payload=payload, state=state)
        self.repository.append_event(event)
        await self.event_bus.publish(event)


def _validate_public_region(region: VisualRegion) -> str | None:
    if region.x < 0 or region.y < 0 or region.width <= 0 or region.height <= 0:
        return "invalid_capture_region"
    if region.width * region.height > 12_000_000:
        return "capture_region_too_large"
    return None


def _error_code(exc: Exception) -> str:
    return exc.args[0] if exc.args and isinstance(exc.args[0], str) else exc.__class__.__name__
