"""Topology-aware local/satellite perception routing."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from ..contracts import DesktopContextSnapshot, DeviceIdentity, ScreenObservation, VisualElement, VisualRegion
from ..devices.satellite.contracts import SatelliteCommand
from ..devices.satellite.registry import WindowsSatelliteRegistry
from ..devices.satellite.transport import SatelliteTransportService
from .windows import WindowsDesktopProvider


class DesktopPerceptionRouter:
    """Select one existing local provider or the existing typed satellite transport."""

    def __init__(self, local: object, satellite: WindowsSatelliteRegistry, transport: SatelliteTransportService) -> None:
        self.local = local
        self.satellite = satellite
        self.transport = transport

    def adapter_for(self, target: DeviceIdentity) -> str:
        return "satellite" if self.satellite.session_for_device(target.device_id) is not None else "local"

    async def desktop_context(self, target: DeviceIdentity, *, owner_id: str, session_id: str, force_satellite: bool = False) -> DesktopContextSnapshot:
        adapter = self.adapter_for(target)
        if force_satellite and adapter != "satellite":
            raise RuntimeError("perception_target_offline")
        if adapter == "satellite":
            connection = self.satellite.session_for_device(target.device_id)
            if connection is None:
                raise RuntimeError("perception_target_offline")
            command = SatelliteCommand(
                f"perception-{uuid4()}", "perception", "perception.screen",
                {"operation": "observe_desktop_context"}, True, "2",
            )
            result = await self.transport.dispatch(owner_id, target.device_id, connection.session_id, command)
            if result.status != "completed":
                raise RuntimeError(result.error_code or "perception_target_offline")
            return _snapshot_from_mapping(result.output, target.device_id)
        provider = self.local
        context = provider.desktop_context(target.device_id) if hasattr(provider, "desktop_context") else DesktopContextSnapshot(f"snapshot-{target.device_id}", target.device_id, datetime.now(UTC), source=getattr(provider, "name", "local"), confidence=0.0)
        if hasattr(context, "__await__"):
            context = await context
        return context

    async def screen(
        self,
        target: DeviceIdentity,
        *,
        owner_id: str,
        session_id: str,
        window_ref: str | None = None,
        region: VisualRegion | None = None,
        mode: str = "screen",
        force_satellite: bool = False,
    ) -> ScreenObservation:
        adapter = self.adapter_for(target)
        if force_satellite and adapter != "satellite":
            raise RuntimeError("perception_target_offline")
        if adapter == "satellite":
            connection = self.satellite.session_for_device(target.device_id)
            if connection is None:
                raise RuntimeError("perception_target_offline")
            parameters: dict[str, object] = {"operation": "observe_screen", "mode": mode}
            if window_ref is not None:
                parameters["window_ref"] = window_ref
            if region is not None:
                parameters["region"] = asdict(region)
            command = SatelliteCommand(
                f"perception-{uuid4()}", "perception", "perception.screen", parameters, True, "2",
            )
            result = await self.transport.dispatch(owner_id, target.device_id, connection.session_id, command)
            if result.status != "completed":
                raise RuntimeError(result.error_code or "perception_target_offline")
            return _observation_from_mapping(result.output, target.device_id)
        provider = self.local
        if mode == "semantic" and hasattr(provider, "desktop_context"):
            context = provider.desktop_context(target.device_id)
            if hasattr(context, "__await__"):
                context = await context
            active = context.active_window
            return ScreenObservation(
                f"observation-{target.device_id}", target.device_id, datetime.now(UTC), getattr(provider, "name", "local"),
                active_window=active.window_ref if active else None,
                confidence=context.confidence,
                metadata={"source": "windows-metadata", "snapshot_id": context.snapshot_id, "semantic": True},
            )
        result = provider.capture(target.device_id, window_ref, region)
        return await result if hasattr(result, "__await__") else result


def _snapshot_from_mapping(value: object, device_id: str) -> DesktopContextSnapshot:
    if isinstance(value, dict) and isinstance(value.get("context"), dict):
        value = value["context"]
    if not isinstance(value, dict):
        raise RuntimeError("invalid_perception_snapshot")
    active = _window_from_mapping(value.get("active_window"))
    windows = tuple(item for item in (_window_from_mapping(item) for item in value.get("windows", ()) if isinstance(item, dict)) if item is not None)
    return DesktopContextSnapshot(
        str(value.get("snapshot_id", f"snapshot-{device_id}")), device_id,
        _datetime(value.get("observed_at")), active, windows,
        _int_or_none(value.get("display_width")), _int_or_none(value.get("display_height")),
        str(value.get("source", "satellite")), float(value.get("confidence", 0.0)),
    )


def _observation_from_mapping(value: object, device_id: str) -> ScreenObservation:
    if isinstance(value, dict) and isinstance(value.get("observation"), dict):
        value = value["observation"]
    if not isinstance(value, dict):
        raise RuntimeError("invalid_perception_observation")
    region = value.get("region")
    return ScreenObservation(
        str(value.get("observation_id", f"observation-{device_id}")), device_id,
        _datetime(value.get("captured_at")), str(value.get("source", "satellite")),
        _int_or_none(value.get("width")), _int_or_none(value.get("height")),
        value.get("active_window") if isinstance(value.get("active_window"), str) else None,
        value.get("text") if isinstance(value.get("text"), str) else None,
        tuple(_element_from_mapping(item) for item in value.get("elements", ()) if isinstance(item, dict)),
        VisualRegion(**region) if isinstance(region, dict) else None,
        False, float(value.get("confidence", 0.0)), value.get("metadata", {}) if isinstance(value.get("metadata"), dict) else {},
    )


def _window_from_mapping(value: object):
    from ..contracts import DesktopWindow

    if not isinstance(value, dict):
        return None
    region = value.get("region")
    return DesktopWindow(
        str(value.get("window_ref", "window-unknown")),
        value.get("title") if isinstance(value.get("title"), str) else None,
        value.get("process_name") if isinstance(value.get("process_name"), str) else None,
        _int_or_none(value.get("process_id")), value.get("window_class") if isinstance(value.get("window_class"), str) else None,
        VisualRegion(**region) if isinstance(region, dict) else None,
        bool(value.get("visible", True)), bool(value.get("active", False)),
    )


def _element_from_mapping(value: dict[str, object]) -> VisualElement:
    region = value.get("region")
    return VisualElement(
        str(value.get("role", "unknown")),
        value.get("label") if isinstance(value.get("label"), str) else None,
        VisualRegion(**region) if isinstance(region, dict) else None,
        float(value.get("confidence", 0.0)), str(value.get("source", "satellite")),
    )


def _datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return datetime.now(UTC)


def _int_or_none(value: object) -> int | None:
    return int(value) if isinstance(value, (int, float)) else None
