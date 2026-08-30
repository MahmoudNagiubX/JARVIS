"""Internal transient pixel buffers used only during one perception request."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ..contracts import VisualRegion


@dataclass(slots=True)
class TransientFrame:
    """A deliberately non-serializable-by-policy frame with explicit release."""

    width: int
    height: int
    pixel_format: str
    captured_at: datetime
    region: VisualRegion
    data: bytearray | memoryview
    released: bool = False

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("frame dimensions must be positive")
        if self.width * self.height > 12_000_000:
            raise ValueError("frame exceeds pixel safety cap")

    def release(self) -> None:
        if self.released:
            return
        if isinstance(self.data, bytearray):
            self.data[:] = b"\x00" * len(self.data)
        else:
            try:
                self.data[:] = b"\x00" * len(self.data)
            except (TypeError, ValueError):
                pass
        self.data = bytearray()
        self.released = True

    def __enter__(self) -> "TransientFrame":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.release()


async def analyze_and_release(
    frame: TransientFrame,
    analyzer: Callable[[TransientFrame], Any | Awaitable[Any]],
) -> Any:
    """Run an analyzer and release the raw buffer on both success and failure."""

    try:
        result = analyzer(frame)
        if isinstance(result, Awaitable):
            result = await result
        return result
    finally:
        frame.release()


def frame_metadata(frame: TransientFrame, digest: str) -> dict[str, object]:
    """Return safe derived metadata after a frame has been released."""

    return {
        "width": frame.width,
        "height": frame.height,
        "pixel_format": frame.pixel_format,
        "captured_at": frame.captured_at.astimezone(UTC).isoformat(),
        "region": {
            "x": frame.region.x,
            "y": frame.region.y,
            "width": frame.region.width,
            "height": frame.region.height,
        },
        "frame_digest": digest,
        "raw_retained": False,
    }
