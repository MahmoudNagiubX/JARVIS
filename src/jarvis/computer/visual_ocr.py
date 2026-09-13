"""Product-owned, read-only local OCR visual-grounding adapter (Batch 05
Milestone 1, GAP-0103 - advances to `PARTIAL`, never `RESOLVED` by this
batch).

This is an execution provider, not an authority: it sits behind
`ComputerActionService`/`WindowsNativeComputerController` exactly like
`WindowsUIAutomationAdapter`/`WindowsNativeInputAdapter`, reuses the
existing bounded GDI capture (`WindowsDesktopProvider.capture_frame`/
`TransientFrame`) rather than implementing a second screenshot subsystem,
and reuses the existing fail-closed window/element privacy and staleness
checks (`validate_input_window`, `resolve_actionable_target`) rather than
re-deriving a second sensitivity policy.

Deliberately read-only and observation-only this batch:

- no `x`/`y`/width/height/path/URL/base64 input from the model - captures
  are derived strictly from a trusted, previously-issued `window_ref`/
  `element_ref`;
- OCR text is untrusted perceptual data - it is returned as a plain string
  field in a tool result like any other read, never specially parsed,
  never able to create an approval, alter policy, or become durable Memory
  on its own;
- raw screenshot/crop pixel bytes are memory-only and released immediately
  after OCR completes (`perception.frame.analyze_and_release`) - never
  SQLite, Memory, World State, audit payload, logs, or an approval preview
  (this action is never consequential, so no approval is ever created for
  it at all);
- opaque `visual-<uuid>` references are observation-only: nothing in this
  batch resolves or accepts one as a targeting input, and every existing
  pointer/keyboard/file/semantic-act parameter validator already rejects a
  `visual-` prefixed string outright (it never matches the required
  `element-`/`window-` prefix) - proven by regression tests, not a new
  actuation code path;
- the optional `easyocr` dependency (`computer-ocr` extra) is imported
  lazily and only inside this module - core JARVIS startup and every other
  Computer Use capability work unchanged when it is absent, returning a
  typed `visual_ocr_not_available` result rather than an import crash.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Callable
from uuid import uuid4

from ..contracts.semantic_ui import SemanticDesktopAdapter
from ..contracts.visual_ui import VisualBounds, VisualObservation, VisualTextRegion
from ..perception.frame import analyze_and_release
from ..perception.windows import WindowsDesktopProvider

try:
    import easyocr as _easyocr
except ImportError:  # pragma: no cover - exercised via the dependency-unavailable tests
    _easyocr = None

PROVIDER_NAME = "local-easyocr"
MAX_REGIONS = 100
MAX_TEXT_PER_REGION = 512
MAX_TOTAL_TEXT = 12_000
# Within the task's reviewed 15-30 second range.
VISUAL_REF_TTL_SECONDS = 20
MAX_VISUAL_REFS = 500


@dataclass(slots=True)
class VisualResult:
    status: str
    output: dict[str, object]
    error_code: str | None = None
    verified: bool = False


@dataclass(slots=True)
class _VisualRefEntry:
    """Internal-only, never exposed to the model. Kept for forward
    compatibility with a future (separately reviewed) batch that might
    resolve a visual ref for grounded re-verification - nothing in Batch 05
    ever looks one up, since visual refs are observation-only here."""

    source_window_ref: str
    text_digest: str
    bounds: VisualBounds
    expires_at: datetime


def _normalize_confidence(value: Any) -> float | None:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return None
    if confidence != confidence or confidence in (float("inf"), float("-inf")):  # NaN/inf check
        return None
    return max(0.0, min(1.0, confidence))


class EasyOcrVisualAdapter:
    """Read-only OCR visual grounding, reusing the existing perception
    (capture) and semantic (element bounds/privacy) authorities - never a
    second copy of either."""

    name = PROVIDER_NAME

    def __init__(
        self,
        perception_provider: WindowsDesktopProvider,
        semantic_adapter: SemanticDesktopAdapter,
        *,
        reader_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.perception_provider = perception_provider
        self.semantic_adapter = semantic_adapter
        self._reader_factory = reader_factory or self._default_reader_factory
        self._reader: Any | None = None
        # `reader_factory` is only ever injected by tests (a fake OCR
        # engine) - in that case treat the provider as available even
        # without the real `easyocr` package installed, matching the
        # existing `WindowsUIAutomationAdapter`/native-input test pattern
        # of injecting a fake behind the same `available` gate.
        self.available = _easyocr is not None or reader_factory is not None
        self._visual_refs: dict[str, _VisualRefEntry] = {}

    @staticmethod
    def _default_reader_factory() -> Any:
        assert _easyocr is not None
        return _easyocr.Reader(["ar", "en"], gpu=False, verbose=False)

    def _ensure_reader(self) -> Any:
        if self._reader is None:
            self._reader = self._reader_factory()
        return self._reader

    async def ocr_window(self, window_ref: str) -> VisualResult:
        if not self.available:
            return VisualResult("failed", {}, "visual_ocr_not_available")
        try:
            self.perception_provider.validate_input_window(window_ref)
        except ValueError as exc:
            reason = str(exc) or "uia_window_stale"
            status = "denied" if reason == "sensitive_window_denied" else "failed"
            return VisualResult(status, {}, reason)
        try:
            frame = self.perception_provider.capture_frame(mode="active_window", window_ref=window_ref)
        except (ValueError, OSError, RuntimeError) as exc:
            return VisualResult("failed", {}, f"visual_capture_failed:{exc.__class__.__name__}")

        async def analyze(active_frame: Any) -> tuple[list[tuple[Any, str, float]], int, int]:
            image = _frame_to_bgr_array(active_frame)
            # The CPU-bound EasyOCR inference itself runs in a worker
            # thread - `analyze_and_release` awaits this coroutine before
            # releasing the frame in its `finally` block, so the frame
            # stays valid for the whole call and is still released exactly
            # once, on the calling (event loop) thread.
            ocr_results = await _run_in_thread(self._run_ocr, image)
            return ocr_results, active_frame.region.x, active_frame.region.y

        try:
            raw_results, origin_x, origin_y = await analyze_and_release(frame, analyze)
        except Exception as exc:
            return VisualResult("failed", {}, f"visual_ocr_inference_failed:{exc.__class__.__name__}")

        observation = self._build_observation(window_ref, raw_results, origin_x, origin_y)
        return VisualResult("succeeded", _observation_to_output(observation), verified=True)

    async def ocr_element(self, element_ref: str) -> VisualResult:
        if not self.available:
            return VisualResult("failed", {}, "visual_ocr_not_available")
        result = await self.semantic_adapter.resolve_actionable_target(element_ref)
        if result.status != "succeeded":
            return VisualResult(_status_for(result.error_code), {}, result.error_code or "uia_target_unavailable")
        element = result.output.get("element") if isinstance(result.output, dict) else None
        bounds = getattr(element, "bounds", None) if element is not None else None
        window_ref = getattr(element, "window_ref", None) if element is not None else None
        if bounds is None or not window_ref:
            return VisualResult("failed", {}, "visual_target_bounds_unavailable")
        try:
            frame = self.perception_provider.capture_frame(mode="active_window", window_ref=window_ref)
        except (ValueError, OSError, RuntimeError) as exc:
            return VisualResult("failed", {}, f"visual_capture_failed:{exc.__class__.__name__}")

        crop_x = max(0, bounds.x - frame.region.x)
        crop_y = max(0, bounds.y - frame.region.y)
        crop_w = min(bounds.width, frame.width - crop_x)
        crop_h = min(bounds.height, frame.height - crop_y)
        if crop_w <= 0 or crop_h <= 0:
            frame.release()
            return VisualResult("failed", {}, "visual_target_bounds_unavailable")

        async def analyze(active_frame: Any) -> list[tuple[Any, str, float]]:
            image = _frame_to_bgr_array(active_frame, crop=(crop_x, crop_y, crop_w, crop_h))
            return await _run_in_thread(self._run_ocr, image)

        try:
            raw_results = await analyze_and_release(frame, analyze)
        except Exception as exc:
            return VisualResult("failed", {}, f"visual_ocr_inference_failed:{exc.__class__.__name__}")

        # Region coordinates from `readtext` are relative to the cropped
        # image - offset back to the crop's screen-absolute origin so the
        # (internal-only) stored bounds remain meaningful, even though the
        # model-facing output never surfaces them.
        observation = self._build_observation(
            window_ref, raw_results, frame.region.x + crop_x, frame.region.y + crop_y,
        )
        return VisualResult("succeeded", _observation_to_output(observation), verified=True)

    def _run_ocr(self, image: Any) -> list[tuple[Any, str, float]]:
        reader = self._ensure_reader()
        return list(reader.readtext(image, detail=1))

    def _build_observation(
        self, source_window_ref: str, raw_results: list[tuple[Any, str, float]], origin_x: int, origin_y: int,
    ) -> VisualObservation:
        now = datetime.now(UTC)
        self._prune_visual_refs(now)
        regions: list[VisualTextRegion] = []
        total_chars = 0
        truncated = False
        for bbox, text, confidence in raw_results:
            if len(regions) >= MAX_REGIONS:
                truncated = True
                break
            normalized_confidence = _normalize_confidence(confidence)
            if normalized_confidence is None:
                continue
            bounded_text = _normalize_text(text)[:MAX_TEXT_PER_REGION]
            if not bounded_text:
                continue
            if total_chars + len(bounded_text) > MAX_TOTAL_TEXT:
                truncated = True
                break
            total_chars += len(bounded_text)
            region_bounds = _bbox_to_bounds(bbox, origin_x, origin_y)
            visual_ref = f"visual-{uuid4()}"
            self._store_visual_ref(visual_ref, source_window_ref, bounded_text, region_bounds, now)
            regions.append(VisualTextRegion(visual_ref, bounded_text, normalized_confidence, region_bounds, now))
        return VisualObservation(source_window_ref, tuple(regions), truncated, PROVIDER_NAME, now)

    def _store_visual_ref(
        self, visual_ref: str, source_window_ref: str, text: str, bounds: VisualBounds, now: datetime,
    ) -> None:
        digest = _text_digest(text)
        self._visual_refs[visual_ref] = _VisualRefEntry(source_window_ref, digest, bounds, now + timedelta(seconds=VISUAL_REF_TTL_SECONDS))
        while len(self._visual_refs) > MAX_VISUAL_REFS:
            self._visual_refs.pop(next(iter(self._visual_refs)))

    def _prune_visual_refs(self, now: datetime) -> None:
        for ref, entry in tuple(self._visual_refs.items()):
            if entry.expires_at <= now:
                self._visual_refs.pop(ref, None)


def _status_for(error_code: str | None) -> str:
    if error_code in {"sensitive_window_denied", "uia_sensitive_value_denied", "uia_element_identity_weak", "uia_target_not_interactable"}:
        return "denied"
    return "failed"


def _normalize_text(text: str) -> str:
    return unicodedata.normalize("NFKC", str(text)).strip()


def _text_digest(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _bbox_to_bounds(bbox: Any, origin_x: int, origin_y: int) -> VisualBounds:
    """`readtext(detail=1)` bounding boxes are 4 corner points, pixel
    coordinates relative to the array passed in - converts to one bounded
    rectangle and offsets it to the screen-absolute origin of whatever was
    captured (internal-only; never surfaced to the model)."""
    try:
        xs = [float(point[0]) for point in bbox]
        ys = [float(point[1]) for point in bbox]
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        return VisualBounds(origin_x + round(x0), origin_y + round(y0), max(0, round(x1 - x0)), max(0, round(y1 - y0)))
    except (TypeError, ValueError, IndexError):
        return VisualBounds(origin_x, origin_y, 0, 0)


def _frame_to_bgr_array(frame: Any, *, crop: tuple[int, int, int, int] | None = None) -> Any:
    """Raw BGRA32 GDI pixel bytes -> a BGR numpy array (matching OpenCV's/
    EasyOCR's default channel order, no extra conversion needed) - never a
    second screenshot subsystem, this consumes the exact bytes
    `WindowsDesktopProvider.capture_frame` already produced. `numpy` is
    only ever imported here, lazily, alongside the optional `easyocr`
    dependency."""
    import numpy as np

    array = np.frombuffer(bytes(frame.data), dtype=np.uint8).reshape(frame.height, frame.width, 4)
    bgr = array[:, :, :3]
    if crop is not None:
        x, y, w, h = crop
        bgr = bgr[y:y + h, x:x + w]
    return np.ascontiguousarray(bgr)


def _observation_to_output(observation: VisualObservation) -> dict[str, object]:
    """Model-facing shape - deliberately never includes raw bounds/x/y for
    any region (the visual-reference payload carries no screen
    coordinates)."""
    return {
        "source_window_ref": observation.source_window_ref,
        "regions": [
            {"visual_ref": region.visual_ref, "text": region.text, "confidence": round(region.confidence, 3)}
            for region in observation.regions
        ],
        "truncated": observation.truncated,
        "provider": observation.provider,
    }


async def _run_in_thread(func: Callable[..., Any], *args: Any) -> Any:
    import asyncio

    return await asyncio.to_thread(func, *args)
