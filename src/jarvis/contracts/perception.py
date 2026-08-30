"""On-demand visual perception contracts; raw frames are not durable state."""

from __future__ import annotations

from collections.abc import Awaitable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol


@dataclass(frozen=True, slots=True)
class VisualRegion:
    x: int
    y: int
    width: int
    height: int


class PerceptionPrivacyMode(StrEnum):
    OFF = "off"
    METADATA_ONLY = "metadata_only"
    ON_DEMAND = "on_demand"


@dataclass(frozen=True, slots=True)
class DesktopWindow:
    """Bounded, ephemeral metadata for one currently visible window."""

    window_ref: str
    title: str | None = None
    process_name: str | None = None
    process_id: int | None = None
    window_class: str | None = None
    region: VisualRegion | None = None
    visible: bool = True
    active: bool = False


@dataclass(frozen=True, slots=True)
class DesktopContextSnapshot:
    """A bounded desktop metadata observation; it never contains pixels."""

    snapshot_id: str
    device_id: str
    observed_at: datetime
    active_window: DesktopWindow | None = None
    windows: tuple[DesktopWindow, ...] = ()
    display_width: int | None = None
    display_height: int | None = None
    source: str = "unknown"
    confidence: float = 0.0

    def __post_init__(self) -> None:
        if len(self.windows) > 50:
            raise ValueError("desktop window list is bounded to 50")
        for window in self.windows:
            if window.title is not None and len(window.title) > 300:
                raise ValueError("window title is bounded to 300 characters")
            if window.process_name is not None and len(window.process_name) > 200:
                raise ValueError("process name is bounded to 200 characters")
        if self.display_width is not None and self.display_width <= 0:
            raise ValueError("display width must be positive")
        if self.display_height is not None and self.display_height <= 0:
            raise ValueError("display height must be positive")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("perception confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class VisualElement:
    role: str
    label: str | None = None
    region: VisualRegion | None = None
    confidence: float = 0.0
    source: str = "unknown"


@dataclass(frozen=True, slots=True)
class ScreenObservation:
    observation_id: str
    device_id: str
    captured_at: datetime
    source: str
    width: int | None = None
    height: int | None = None
    active_window: str | None = None
    text: str | None = None
    elements: tuple[VisualElement, ...] = ()
    region: VisualRegion | None = None
    raw_retained: bool = False
    confidence: float = 0.0
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CameraObservation:
    observation_id: str
    device_id: str
    captured_at: datetime
    source: str
    retained: bool = False


@dataclass(frozen=True, slots=True)
class PerceptionResult:
    status: str
    observation: ScreenObservation | None = None
    error_code: str | None = None
    context: DesktopContextSnapshot | None = None


class PerceptionProvider(Protocol):
    name: str
    available: bool

    async def capture(self, device_id: str, window: str | None = None, region: VisualRegion | None = None) -> ScreenObservation: ...

    def desktop_context(self, device_id: str) -> DesktopContextSnapshot: ...


class OCRProvider(Protocol):
    name: str
    available: bool

    async def extract(self, observation: ScreenObservation) -> ScreenObservation: ...
