"""Product-owned local OCR visual-grounding adapter (Batch 05/08,
GAP-0103/GAP-0102 - still `PARTIAL`, never `RESOLVED` by this module alone).

This is an execution provider, not an authority: it sits behind
`ComputerActionService`/`WindowsNativeComputerController` exactly like
`WindowsUIAutomationAdapter`/`WindowsNativeInputAdapter`, reuses the
existing bounded GDI capture (`WindowsDesktopProvider.capture_frame`/
`TransientFrame`) rather than implementing a second screenshot subsystem,
and reuses the existing fail-closed window/element privacy and staleness
checks (`validate_input_window`, `resolve_actionable_target`) rather than
re-deriving a second sensitivity policy.

The OCR observation itself remains read-only. Batch 08 adds one separately
reviewed, bounded visual action: a window-origin ``visual_ref`` may be
revalidated and passed to the existing native click layer. Element-origin
visual refs remain observation-only because semantic UIA targeting is the
preferred actuation path.

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
- opaque `visual-<uuid>` references never expose coordinates or raw geometry
  to the model. Only a window-origin ref can enter the separately reviewed
  visual-click resolver; element-origin refs are rejected with a typed
  semantic-target preference error;
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

import hashlib
import unicodedata
from collections.abc import Mapping
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
# At the upper end of the task's reviewed 15-30 second range so the
# approval-bound visual path can complete its bounded OCR revalidations on a
# CPU-only host without extending the reference after issuance.
VISUAL_REF_TTL_SECONDS = 30
MAX_VISUAL_REFS = 500
# Fixed, reviewed actuation confidence gate. This is deliberately not a
# dynamic threshold derived from the current frame or candidate count.
VISUAL_ACTUATION_MIN_CONFIDENCE = 0.60
VISUAL_SPATIAL_IOU_MIN = 0.20
VISUAL_SPATIAL_CONTEXT_MAX_CENTER_DISTANCE = 180

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


@dataclass(frozen=True, slots=True)
class VisualTarget:
    """Trusted internal target; ``bounds`` never crosses the model boundary."""

    visual_ref: str
    source_window_ref: str
    source_window_identity_digest: str
    normalized_text_digest: str
    bounds: VisualBounds
    confidence: float
    origin_kind: str
    observed_at: datetime
    expires_at: datetime
    window_title: str | None
    process_name: str | None
    binding_digest: str


@dataclass(slots=True)
class VisualTargetResult:
    """Internal resolver result with typed, non-sensitive failure reasons."""

    status: str
    target: VisualTarget | None = None
    error_code: str | None = None

    def public_output(self) -> dict[str, object]:
        """Return only bounded metadata needed by the approval authority."""
        if self.target is None:
            return {}
        return {
            "visual_ref": self.target.visual_ref,
            "source_window_ref": self.target.source_window_ref,
            "source_window_identity_digest": self.target.source_window_identity_digest,
            "title": self.target.window_title,
            "process_name": self.target.process_name,
            "reference_expires_at": self.target.expires_at,
            "binding_digest": self.target.binding_digest,
        }


@dataclass(slots=True)
class _VisualRefEntry:
    """Internal-only provenance held in the existing visual-ref store."""

    source_window_ref: str
    source_window_identity_digest: str | None
    normalized_text_digest: str
    bounds: VisualBounds
    confidence: float
    origin_kind: str
    observed_at: datetime
    expires_at: datetime

    @property
    def text_digest(self) -> str:
        """Compatibility alias for the pre-Batch-08 internal field name."""
        return self.normalized_text_digest


@dataclass(frozen=True, slots=True)
class _FreshWindowOcr:
    raw_results: list[tuple[Any, str, float]]
    origin_x: int
    origin_y: int
    source_window_identity_digest: str | None
    window_title: str | None
    process_name: str | None


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
        fresh, error_code = await self._capture_window_ocr(window_ref)
        if fresh is None:
            return VisualResult(_status_for(error_code), {}, error_code or "visual_capture_failed")
        observation = self._build_observation(
            window_ref,
            fresh.raw_results,
            fresh.origin_x,
            fresh.origin_y,
            source_window_identity_digest=fresh.source_window_identity_digest,
            origin_kind="window",
        )
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
            self.perception_provider.validate_input_window(window_ref)
        except ValueError as exc:
            reason = str(exc) or "uia_window_stale"
            return VisualResult(_status_for(reason), {}, reason)
        source_identity_digest, _title, _process_name, source_error = self._describe_source_window(window_ref)
        if source_error is not None:
            return VisualResult(_status_for(source_error), {}, source_error)
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
            window_ref,
            raw_results,
            frame.region.x + crop_x,
            frame.region.y + crop_y,
            source_window_identity_digest=source_identity_digest,
            origin_kind="element",
        )
        return VisualResult("succeeded", _observation_to_output(observation), verified=True)

    async def _capture_window_ocr(self, window_ref: str) -> tuple[_FreshWindowOcr | None, str | None]:
        """Capture and OCR one fresh active window without creating refs.

        The same GDI/privacy/EasyOCR path serves observation and visual-ref
        revalidation. Revalidation consumes the result in memory only and
        never appends a second reference store or emits a new model result.
        """
        try:
            self.perception_provider.validate_input_window(window_ref)
        except ValueError as exc:
            reason = str(exc) or "uia_window_stale"
            return None, reason
        source_identity_digest, title, process_name, source_error = self._describe_source_window(window_ref)
        if source_error is not None:
            return None, source_error
        try:
            frame = self.perception_provider.capture_frame(mode="active_window", window_ref=window_ref)
        except (ValueError, OSError, RuntimeError) as exc:
            return None, f"visual_capture_failed:{exc.__class__.__name__}"

        async def analyze(active_frame: Any) -> tuple[list[tuple[Any, str, float]], int, int]:
            image = _frame_to_bgr_array(active_frame)
            ocr_results = await _run_in_thread(self._run_ocr, image)
            return ocr_results, active_frame.region.x, active_frame.region.y

        try:
            raw_results, origin_x, origin_y = await analyze_and_release(frame, analyze)
        except _OcrModelsUnavailableError:
            return None, "visual_ocr_models_unavailable"
        except Exception as exc:
            return None, f"visual_ocr_inference_failed:{exc.__class__.__name__}"
        return _FreshWindowOcr(
            list(raw_results), origin_x, origin_y, source_identity_digest, title, process_name,
        ), None

    def _describe_source_window(
        self, window_ref: str,
    ) -> tuple[str | None, str | None, str | None, str | None]:
        """Read trusted source identity when the provider supports it.

        Older injected read-only test providers deliberately have no window
        descriptor. That remains valid for OCR observation. Visual actuation
        fails closed later if the stored provenance lacks this identity.
        """
        describe = getattr(self.perception_provider, "describe_window", None)
        if not callable(describe):
            return None, None, None, None
        try:
            descriptor = describe(window_ref)
        except ValueError as exc:
            return None, None, None, str(exc) or "window_ref_expired"
        if not isinstance(descriptor, Mapping):
            return None, None, None, "visual_source_identity_unavailable"
        identity_digest = descriptor.get("identity_digest")
        if not isinstance(identity_digest, str) or not identity_digest:
            return None, None, None, "visual_source_identity_unavailable"
        title = descriptor.get("title")
        process_name = descriptor.get("process_name")
        return (
            identity_digest,
            title if isinstance(title, str) else None,
            process_name if isinstance(process_name, str) else None,
            None,
        )

    def _run_ocr(self, image: Any) -> list[tuple[Any, str, float]]:
        reader = self._ensure_reader()
        return list(reader.readtext(image, detail=1))

    def _build_observation(
        self,
        source_window_ref: str,
        raw_results: list[tuple[Any, str, float]],
        origin_x: int,
        origin_y: int,
        *,
        source_window_identity_digest: str | None = None,
        origin_kind: str = "window",
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
            self._store_visual_ref(
                visual_ref,
                source_window_ref,
                bounded_text,
                region_bounds,
                normalized_confidence,
                now,
                source_window_identity_digest=source_window_identity_digest,
                origin_kind=origin_kind,
            )
            regions.append(VisualTextRegion(visual_ref, bounded_text, normalized_confidence, region_bounds, now))
        return VisualObservation(source_window_ref, tuple(regions), truncated, PROVIDER_NAME, now)

    def _store_visual_ref(
        self,
        visual_ref: str,
        source_window_ref: str,
        text: str,
        bounds: VisualBounds,
        confidence: float,
        now: datetime,
        *,
        source_window_identity_digest: str | None,
        origin_kind: str,
    ) -> None:
        normalized_text = _normalize_ref_text(text)
        self._visual_refs[visual_ref] = _VisualRefEntry(
            source_window_ref=source_window_ref,
            source_window_identity_digest=source_window_identity_digest,
            normalized_text_digest=_text_digest(normalized_text),
            bounds=bounds,
            confidence=confidence,
            origin_kind=origin_kind,
            observed_at=now,
            expires_at=now + timedelta(seconds=VISUAL_REF_TTL_SECONDS),
        )
        while len(self._visual_refs) > MAX_VISUAL_REFS:
            self._visual_refs.pop(next(iter(self._visual_refs)))

    async def resolve_visual_ref(self, visual_ref: str) -> VisualTargetResult:
        """Resolve one opaque ref against a fresh, unique OCR observation.

        This is an internal provider operation. It deliberately returns a
        trusted target object only to the controller; ``public_output`` is
        metadata-only and cannot expose OCR text or geometry.
        """
        if not isinstance(visual_ref, str) or not visual_ref.startswith("visual-"):
            return VisualTargetResult("failed", error_code="visual_ref_unknown")
        now = datetime.now(UTC)
        entry = self._visual_refs.get(visual_ref)
        if entry is not None and entry.expires_at <= now:
            self._visual_refs.pop(visual_ref, None)
            return VisualTargetResult("failed", error_code="visual_ref_expired")
        self._prune_visual_refs(now)
        entry = self._visual_refs.get(visual_ref)
        if entry is None:
            return VisualTargetResult("failed", error_code="visual_ref_unknown")
        if entry.origin_kind != "window":
            return VisualTargetResult("denied", error_code="visual_semantic_target_preferred")
        if entry.confidence < VISUAL_ACTUATION_MIN_CONFIDENCE:
            return VisualTargetResult("denied", error_code="visual_target_confidence_too_low")
        if not entry.source_window_identity_digest:
            return VisualTargetResult("failed", error_code="visual_source_identity_unavailable")

        fresh, error_code = await self._capture_window_ocr(entry.source_window_ref)
        if fresh is None:
            return VisualTargetResult(_status_for(error_code), error_code=error_code or "visual_capture_failed")
        if fresh.source_window_identity_digest != entry.source_window_identity_digest:
            return VisualTargetResult("failed", error_code="visual_source_identity_changed")

        matching: list[tuple[VisualBounds, float]] = []
        same_text_seen = False
        low_confidence_seen = False
        for bbox, text, confidence in fresh.raw_results:
            bounded_text = _normalize_text(text)[:MAX_TEXT_PER_REGION]
            if not bounded_text:
                continue
            if _text_digest(_normalize_ref_text(bounded_text)) != entry.normalized_text_digest:
                continue
            same_text_seen = True
            normalized_confidence = _normalize_confidence(confidence)
            if normalized_confidence is None:
                continue
            if normalized_confidence < VISUAL_ACTUATION_MIN_CONFIDENCE:
                low_confidence_seen = True
                continue
            current_bounds = _bbox_to_bounds(bbox, fresh.origin_x, fresh.origin_y)
            if current_bounds.width <= 0 or current_bounds.height <= 0:
                continue
            if _spatially_continuous(entry.bounds, current_bounds):
                matching.append((current_bounds, normalized_confidence))

        if not matching:
            if same_text_seen and low_confidence_seen:
                return VisualTargetResult("denied", error_code="visual_target_confidence_too_low")
            if same_text_seen:
                return VisualTargetResult("failed", error_code="visual_target_not_found")
            return VisualTargetResult("failed", error_code="visual_target_text_changed")
        if len(matching) != 1:
            return VisualTargetResult("failed", error_code="visual_target_ambiguous")

        bounds, confidence = matching[0]
        binding_digest = _visual_binding_digest(
            visual_ref,
            entry.source_window_ref,
            entry.source_window_identity_digest,
            entry.normalized_text_digest,
            entry.origin_kind,
            entry.expires_at,
        )
        return VisualTargetResult(
            "succeeded",
            target=VisualTarget(
                visual_ref=visual_ref,
                source_window_ref=entry.source_window_ref,
                source_window_identity_digest=entry.source_window_identity_digest,
                normalized_text_digest=entry.normalized_text_digest,
                bounds=bounds,
                confidence=confidence,
                origin_kind=entry.origin_kind,
                observed_at=entry.observed_at,
                expires_at=entry.expires_at,
                window_title=fresh.window_title,
                process_name=fresh.process_name,
                binding_digest=binding_digest,
            ),
        )

    async def revalidate_visual_ref(self, visual_ref: str, expected: VisualTarget) -> VisualTargetResult:
        """Re-read the ref and preserve its source/text binding after focus."""
        result = await self.resolve_visual_ref(visual_ref)
        if result.target is None:
            return result
        target = result.target
        if (
            target.visual_ref != expected.visual_ref
            or target.source_window_ref != expected.source_window_ref
            or target.source_window_identity_digest != expected.source_window_identity_digest
            or target.normalized_text_digest != expected.normalized_text_digest
            or target.origin_kind != expected.origin_kind
            or target.binding_digest != expected.binding_digest
        ):
            return VisualTargetResult("failed", error_code="visual_target_changed")
        return result

    def _prune_visual_refs(self, now: datetime) -> None:
        for ref, entry in tuple(self._visual_refs.items()):
            if entry.expires_at <= now:
                self._visual_refs.pop(ref, None)


def _status_for(error_code: str | None) -> str:
    if error_code in {
        "sensitive_window_denied",
        "uia_sensitive_value_denied",
        "uia_element_identity_weak",
        "uia_target_not_interactable",
        "visual_semantic_target_preferred",
        "visual_target_confidence_too_low",
    }:
        return "denied"
    return "failed"


def _normalize_text(text: str) -> str:
    return unicodedata.normalize("NFKC", str(text)).strip()


def _normalize_ref_text(text: str) -> str:
    """Normalize only the internal ref identity, preserving model text."""
    return " ".join(unicodedata.normalize("NFKC", str(text)).split())


def _text_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _visual_binding_digest(
    visual_ref: str,
    source_window_ref: str,
    source_window_identity_digest: str,
    normalized_text_digest: str,
    origin_kind: str,
    expires_at: datetime,
) -> str:
    payload = "|".join((
        visual_ref,
        source_window_ref,
        source_window_identity_digest,
        normalized_text_digest,
        origin_kind,
        expires_at.isoformat(),
    ))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _spatially_continuous(previous: VisualBounds, current: VisualBounds) -> bool:
    if previous.width <= 0 or previous.height <= 0 or current.width <= 0 or current.height <= 0:
        return False
    left = max(previous.x, current.x)
    top = max(previous.y, current.y)
    right = min(previous.x + previous.width, current.x + current.width)
    bottom = min(previous.y + previous.height, current.y + current.height)
    intersection = max(0, right - left) * max(0, bottom - top)
    if intersection > 0:
        previous_area = previous.width * previous.height
        current_area = current.width * current.height
        union = previous_area + current_area - intersection
        if union > 0 and intersection / union >= VISUAL_SPATIAL_IOU_MIN:
            return True
    previous_center_x = previous.x + previous.width / 2
    previous_center_y = previous.y + previous.height / 2
    current_center_x = current.x + current.width / 2
    current_center_y = current.y + current.height / 2
    delta_x = previous_center_x - current_center_x
    delta_y = previous_center_y - current_center_y
    return delta_x * delta_x + delta_y * delta_y <= VISUAL_SPATIAL_CONTEXT_MAX_CENTER_DISTANCE ** 2


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
