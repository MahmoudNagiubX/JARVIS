"""Vendor-neutral, read-only visual/OCR grounding contracts (Batch 05
Milestone 1, GAP-0103 - PARTIAL, not RESOLVED).

These are the ONLY objects that may cross the boundary from an OCR provider
adapter (`jarvis.computer.visual_ocr`) into `ComputerActionService`/the
model-facing tool layer - a provider-specific object (an EasyOCR result
tuple, a numpy array, raw image bytes) must never leak beyond the adapter
module. OCR text is untrusted perceptual data: it is never authority, never
self-approves anything, and never becomes durable Memory on its own.

`VisualBounds` exists on `VisualTextRegion` for internal/adapter use only
(e.g. a future batch's actuation-grounding work) - the model-facing tool
result built by `ComputerActionService`/`WindowsNativeComputerController`
must never surface raw x/y/width/height through the visual-reference
payload.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class VisualBounds:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class VisualTextRegion:
    visual_ref: str
    text: str
    confidence: float
    bounds: VisualBounds
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class VisualObservation:
    source_window_ref: str
    regions: tuple[VisualTextRegion, ...]
    truncated: bool
    provider: str
    observed_at: datetime
