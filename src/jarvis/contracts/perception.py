"""On-demand visual perception contracts; raw frames are not durable state."""

from __future__ import annotations

from collections.abc import Awaitable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class VisualRegion:
    x: int
    y: int
    width: int
    height: int


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


class PerceptionProvider(Protocol):
    name: str
    available: bool

    async def capture(self, device_id: str, window: str | None = None, region: VisualRegion | None = None) -> ScreenObservation: ...


class OCRProvider(Protocol):
    name: str
    available: bool

    async def extract(self, observation: ScreenObservation) -> ScreenObservation: ...
