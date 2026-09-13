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

Offline-only by construction (Batch 06, R18B05-001): production
`Reader()` construction always passes `download_enabled=False` plus an
explicit, product-owned `model_storage_directory`/`user_network_directory`
(configured via `JarvisConfig.ocr_model_dir`/`JARVIS_OCR_MODEL_DIR` - never
EasyOCR's own `~/.EasyOCR` default), and `_models_ready()` verifies both
required model weight files already exist on disk *before* `Reader()` is
ever constructed - a read-only, no-approval capability must never be able
to reach the network or create an implicit cache beneath the owner's home,
whether because a model is missing or because it never was. Missing/corrupt
models degrade to a typed `visual_ocr_models_unavailable` result. Model
acquisition itself is a separate, explicitly-invoked, development/setup-only
step - see `scripts/setup/provision_easyocr_models.py` - never triggered by
this module or by core startup.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
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

# Batch 06 (R18B05-001): the exact two EasyOCR 1.7.2 model weight files a
# `Reader(["ar", "en"], detect_network="craft")` construction requires -
# sourced directly from `easyocr.config.detection_models["craft"]` and
# `easyocr.config.recognition_models["gen1"]["arabic_g1"]` (EasyOCR
# automatically selects the "arabic_g1" generation-1 recognition network for
# any lang_list containing "ar", per `Reader.__init__`'s auto-detect
# branch - see `scripts/setup/provision_easyocr_models.py` for the recorded
# download URLs/checksums). Both must already exist on disk before
# `Reader()` is ever constructed - production OCR never downloads anything.
OCR_DETECTION_MODEL_FILENAME = "craft_mlt_25k.pth"
OCR_RECOGNITION_MODEL_FILENAME = "arabic.pth"


class _OcrModelsUnavailableError(Exception):
    """Internal-only marker (Batch 06, R18B05-001): raised when the real
    EasyOCR package itself refuses to proceed without downloading (a
    corrupt/checksum-mismatched model file, caught here rather than let
    `FileNotFoundError` surface as a generic inference failure) - always
    translated to the typed `visual_ocr_models_unavailable` result, never a
    redownload attempt (`download_enabled=False` is always passed)."""


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
        model_dir: str | None = None,
    ) -> None:
        self.perception_provider = perception_provider
        self.semantic_adapter = semantic_adapter
        self.model_dir = model_dir
        self._using_default_factory = reader_factory is None
        self._reader_factory = reader_factory or self._default_reader_factory
        self._reader: Any | None = None
        # `reader_factory` is only ever injected by tests (a fake OCR
        # engine) - in that case treat the provider as available even
        # without the real `easyocr` package installed, matching the
        # existing `WindowsUIAutomationAdapter`/native-input test pattern
        # of injecting a fake behind the same `available` gate.
        self.available = _easyocr is not None or reader_factory is not None
        self._visual_refs: dict[str, _VisualRefEntry] = {}

    def _models_ready(self) -> str | None:
        """Fail-closed, offline-only gate (R18B05-001, Batch 06). Returns
        `None` only when the two required model weight files already exist
        inside a product-owned, explicitly configured directory - EasyOCR's
        own `Reader()` construction is never given the chance to create a
        missing directory (it unconditionally `mkdir`s both
        `model_storage_directory`/`user_network_directory` if they don't
        already exist) or attempt a download. A test-injected fake
        `reader_factory` bypasses this gate entirely - it is never the real
        EasyOCR package, so there is nothing to check."""
        if not self._using_default_factory or self._reader is not None:
            return None
        if not self.model_dir:
            return "visual_ocr_models_unavailable"
        model_root = Path(self.model_dir)
        model_storage_directory = model_root / "model"
        user_network_directory = model_root / "user_network"
        if not model_storage_directory.is_dir() or not user_network_directory.is_dir():
            return "visual_ocr_models_unavailable"
        for filename in (OCR_DETECTION_MODEL_FILENAME, OCR_RECOGNITION_MODEL_FILENAME):
            if not (model_storage_directory / filename).is_file():
                return "visual_ocr_models_unavailable"
        return None

    def _default_reader_factory(self) -> Any:
        assert _easyocr is not None
        assert self.model_dir  # `_models_ready()` gates every call site before this ever runs
        model_root = Path(self.model_dir)
        try:
            return _easyocr.Reader(
                ["ar", "en"], gpu=False, verbose=False,
                model_storage_directory=str(model_root / "model"),
                user_network_directory=str(model_root / "user_network"),
                # The single most important line in this module (R18B05-001):
                # a read-only, no-approval capability must never be able to
                # reach the network, no matter what state the model
                # directory is in.
                download_enabled=False,
            )
        except FileNotFoundError as exc:
            # Defense-in-depth: a file that passed `_models_ready()`'s
            # existence check but fails EasyOCR's own MD5 integrity check
            # (corrupt/mismatched) raises exactly this, with
            # `download_enabled=False` already guaranteeing no redownload
            # was attempted - translate to the same typed result the caller
            # already returns for a missing model.
            raise _OcrModelsUnavailableError(str(exc)) from exc

    def _ensure_reader(self) -> Any:
        if self._reader is None:
            self._reader = self._reader_factory()
        return self._reader

    async def ocr_window(self, window_ref: str) -> VisualResult:
        if not self.available:
            return VisualResult("failed", {}, "visual_ocr_not_available")
        models_error = self._models_ready()
        if models_error is not None:
            return VisualResult("failed", {}, models_error)
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
        except _OcrModelsUnavailableError:
            return VisualResult("failed", {}, "visual_ocr_models_unavailable")
        except Exception as exc:
            return VisualResult("failed", {}, f"visual_ocr_inference_failed:{exc.__class__.__name__}")

        observation = self._build_observation(window_ref, raw_results, origin_x, origin_y)
        return VisualResult("succeeded", _observation_to_output(observation), verified=True)

    async def ocr_element(self, element_ref: str) -> VisualResult:
        if not self.available:
            return VisualResult("failed", {}, "visual_ocr_not_available")
        models_error = self._models_ready()
        if models_error is not None:
            return VisualResult("failed", {}, models_error)
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
        except _OcrModelsUnavailableError:
            return VisualResult("failed", {}, "visual_ocr_models_unavailable")
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
