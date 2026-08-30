"""Capability-driven perception providers with no retained raw image data."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from ..contracts import DesktopContextSnapshot, PerceptionProvider, ScreenObservation, VisualRegion


class DeferredPerceptionProvider:
    name = "deferred"
    available = False

    async def capture(self, device_id: str, window: str | None = None, region: VisualRegion | None = None) -> ScreenObservation:
        del device_id, window, region
        raise RuntimeError("screen_capture_provider_not_configured")

    def desktop_context(self, device_id: str) -> DesktopContextSnapshot:
        return DesktopContextSnapshot(f"snapshot-{uuid4()}", device_id, datetime.now(UTC), source=self.name, confidence=0.0)


class StaticPerceptionProvider:
    """Small deterministic provider useful for local acceptance tests."""

    name = "static-test"
    available = True

    def __init__(self, text: str = "") -> None:
        self.text = text

    async def capture(self, device_id: str, window: str | None = None, region: VisualRegion | None = None) -> ScreenObservation:
        return ScreenObservation(f"observation-{uuid4()}", device_id, datetime.now(UTC), self.name, active_window=window, text=self.text, region=region, raw_retained=False, confidence=1.0)

    def desktop_context(self, device_id: str) -> DesktopContextSnapshot:
        return DesktopContextSnapshot(f"snapshot-{uuid4()}", device_id, datetime.now(UTC), source=self.name, confidence=1.0)
