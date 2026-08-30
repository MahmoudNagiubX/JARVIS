"""Active desktop metadata projection kept separate from durable world state."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from ..contracts import DesktopContextSnapshot, DesktopWindow
from ..world_state.service import DurableWorldStateService
from .cache import ObservationCache


class ActiveDesktopContextService:
    """In-memory latest desktop context with safe metadata-only projection."""

    def __init__(self, world_state: DurableWorldStateService | None = None) -> None:
        self.world_state = world_state
        self._latest: dict[tuple[str, str], tuple[str, DesktopContextSnapshot]] = {}
        self._safe_state: dict[tuple[str, str], dict[str, object]] = {}

    async def update(self, owner_id: str, session_id: str, snapshot: DesktopContextSnapshot) -> DesktopContextSnapshot:
        key = (owner_id, snapshot.device_id)
        safe = self.safe_metadata(snapshot)
        previous = self._safe_state.get(key)
        self._latest[key] = (session_id, snapshot)
        self._safe_state[key] = safe
        if self.world_state is not None and _material_signature(safe) != _material_signature(previous):
            source = snapshot.source
            reference = snapshot.snapshot_id
            await self.world_state.set_fact(owner_id, f"desktop.{snapshot.device_id}.active_app", safe["active_app"], source=source, source_reference=reference, confidence=snapshot.confidence, freshness_seconds=60, device_id=snapshot.device_id)
            await self.world_state.set_fact(owner_id, f"desktop.{snapshot.device_id}.active_workspace", safe["active_workspace"], source=source, source_reference=reference, confidence=snapshot.confidence, freshness_seconds=60, device_id=snapshot.device_id)
            await self.world_state.set_fact(owner_id, f"desktop.{snapshot.device_id}.available", True, source=source, source_reference=reference, confidence=snapshot.confidence, freshness_seconds=60, device_id=snapshot.device_id)
        return snapshot

    def latest(self, owner_id: str, device_id: str, session_id: str) -> DesktopContextSnapshot | None:
        item = self._latest.get((owner_id, device_id))
        return item[1] if item is not None and item[0] == session_id else None

    def safe_context(self, owner_id: str, device_id: str, session_id: str, *, now: datetime | None = None) -> dict[str, object]:
        snapshot = self.latest(owner_id, device_id, session_id)
        if snapshot is None:
            return {"available": False, "active_app": None, "active_workspace": None, "observed_at": None}
        safe = self.safe_metadata(snapshot)
        observed = snapshot.observed_at.astimezone(UTC)
        current = (now or datetime.now(UTC)).astimezone(UTC)
        safe["freshness_seconds"] = max(0.0, (current - observed).total_seconds())
        return safe

    def clear(self) -> None:
        self._latest.clear()
        self._safe_state.clear()

    @staticmethod
    def safe_metadata(snapshot: DesktopContextSnapshot) -> dict[str, object]:
        active = snapshot.active_window
        return {
            "available": True,
            "active_app": (active.process_name if active else None),
            "active_workspace": (active.window_class if active else "desktop"),
            "observed_at": snapshot.observed_at.astimezone(UTC).isoformat(),
            "source": snapshot.source,
            "confidence": snapshot.confidence,
            "device_id": snapshot.device_id,
        }

    @staticmethod
    def public_snapshot(snapshot: DesktopContextSnapshot) -> dict[str, object]:
        """Return bounded metadata while retaining the ephemeral window references."""

        result = asdict(snapshot)
        result["windows"] = [ActiveDesktopContextService.public_window(item) for item in snapshot.windows]
        if snapshot.active_window is not None:
            result["active_window"] = ActiveDesktopContextService.public_window(snapshot.active_window)
        return result

    @staticmethod
    def public_window(window: DesktopWindow) -> dict[str, object]:
        return asdict(window)


class DesktopContextCache(ObservationCache):
    """Compatibility name for callers that want a desktop-specific cache."""


def _material_signature(value: dict[str, object] | None) -> tuple[object, ...] | None:
    if value is None:
        return None
    return tuple(value.get(key) for key in ("available", "active_app", "active_workspace", "source", "confidence", "device_id"))
