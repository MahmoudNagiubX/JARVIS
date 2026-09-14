"""Phase 18 Workstream A Batch 06/07 - opt-in PHYSICAL Arabic/mixed OCR
visual-grounding acceptance runner (GAP-0103).

This is a durable development/evaluation tool, NOT part of production
`AgentRuntime` startup - it is never imported or auto-run by the product.
Unlike `computer_use_acceptance.py`, this runner needs the real optional
`computer-ocr` (`easyocr`/`torch`/`torchvision`) extra installed, so it must
be invoked with an interpreter that has it (an isolated evaluation venv -
never the project's own `.venv`), alongside `computer-uia`
(`uiautomation`, needed for `computer.semantic.read`). It also needs an
already-provisioned, offline EasyOCR model directory (see
`scripts/setup/provision_easyocr_models.py`).

    <isolated-venv>/python scripts/phase18/ocr_visual_acceptance.py --model-dir <path> --out <results.json> --runs 3

Batch 08's evaluation-only candidate switch is bounded to
``combined_ar_en`` (the accepted production reader), ``english_only`` (an
explicitly provisioned comparison reader), and ``combined_then_english`` (a
runner-local two-pass comparison). It does not alter production configuration
or create a model-driven language router:

    <isolated-venv>/python scripts/phase18/ocr_visual_acceptance.py --candidate english_only --model-dir <path> --out <results.json> --runs 3

Safety rules (same discipline as `computer_use_acceptance.py`):

- launches only its own disposable fixture process
  (`uia_ocr_fixture_host.py`), never an owner app, never an owner file,
  never an owner browser/profile;
- the fixture's window title always carries a fresh random nonce
  (`JARVIS-CUV2-OCR-FIXTURE-<uuid>`) - the runner waits only for that
  *exact* title and aborts on a collision, never a "first match" guess;
- cleanup owns the *exact* child PID it launched (`Popen.terminate()` +
  `wait()` + a post-mortem liveness check), never a broad
  `taskkill /IM ...`;
- every OCR call goes through the real `computer.visual.read` tool via the
  real `ComputerActionService` -> `WindowsNativeComputerController` ->
  `EasyOcrVisualAdapter` path - never a direct `easyocr` call bypassing
  product code;
- candidate readers remain local/offline and use explicit model directories;
  Candidate B requires the separately provisioned `english_g2.pth` weight;
  neither candidate accepts a free-form language or model parameter;
- network access is structurally proven impossible, not just assumed: each
  `computer.visual.read` call runs with `socket.socket.connect` patched to
  raise immediately if ever invoked - the whole OCR pipeline (capture,
  offline-gate check, `Reader()` construction if needed, inference) must
  reach zero real network activity;
- results (including Arabic/mixed text) are always written to a UTF-8 file
  (`--out`), never printed as raw Unicode to a Windows console (the
  default `cp1252` codec cannot encode Arabic and crashes on print()).
- the visual-actuation mode permits only its fixed two-attempt pre-input
  focus-race recovery; it never retries after native input begins.

No retry-until-green loop: a run that fails is reported as failed.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import ctypes
import json
import platform
import re
import socket
import subprocess
import sys
import time
import unicodedata
import uuid
from pathlib import Path

REPO_SRC = Path(__file__).resolve().parents[2] / "src"
if str(REPO_SRC) not in sys.path:
    sys.path.insert(0, str(REPO_SRC))
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from owned_fixture_process import launch_owned_fixture, terminate_owned_fixture

FIXTURE_HOST_SCRIPT = Path(__file__).resolve().with_name("uia_ocr_fixture_host.py")

LABEL_READY = "JARVIS OCR fixture ready"
LABEL_ARABIC_GREETING = "مرحبا يا جارفيس"
LABEL_ARABIC_SETTINGS = "الإعدادات"
LABEL_MIXED_SETTINGS = "JARVIS الإعدادات"
LABEL_ENGLISH_ONLY = "JARVIS OCR FIXTURE"
VISUAL_ACTION_LABEL = "GO"
VISUAL_STATUS_READY = "VISUAL STATUS READY"
VISUAL_STATUS_APPLIED = "VISUAL STATUS APPLIED"

OCR_CANDIDATES = ("combined_ar_en", "english_only", "combined_then_english")
CANDIDATE_MODEL_FILES = {
    "combined_ar_en": ("craft_mlt_25k.pth", "arabic.pth"),
    "english_only": ("craft_mlt_25k.pth", "english_g2.pth"),
    "combined_then_english": ("craft_mlt_25k.pth", "arabic.pth", "english_g2.pth"),
}


class _NetworkAccessDuringOcrError(RuntimeError):
    """Raised by the network-block guard if any code reachable from a
    `computer.visual.read` call ever attempts a real socket connection -
    proves the OCR pipeline made zero network access attempts for real,
    not merely that its own offline-gate logic looks correct in isolation."""


def _validate_candidate(candidate: str) -> str:
    if candidate not in OCR_CANDIDATES:
        raise ValueError(f"unsupported OCR candidate: {candidate}")
    return candidate


def _candidate_model_files(candidate: str) -> tuple[str, ...]:
    return CANDIDATE_MODEL_FILES[_validate_candidate(candidate)]


def _candidate_model_error(model_dir: str, candidate: str) -> str | None:
    root = Path(model_dir)
    model_directory = root / "model"
    user_network_directory = root / "user_network"
    if not model_directory.is_dir() or not user_network_directory.is_dir():
        return "candidate_model_directory_unavailable"
    missing = [name for name in _candidate_model_files(candidate) if not (model_directory / name).is_file()]
    return f"candidate_model_missing:{','.join(missing)}" if missing else None


def _candidate_model_metadata(model_dir: str, candidate: str) -> list[dict[str, object]]:
    model_directory = Path(model_dir) / "model"
    return [
        {"name": name, "size_bytes": (model_directory / name).stat().st_size}
        for name in _candidate_model_files(candidate)
    ]


def _process_memory_snapshot() -> dict[str, int] | None:
    """Return a bounded current-process working-set snapshot on Windows.

    This is evaluation-only evidence. It deliberately reports process-level
    working set and peak working set rather than retaining any screenshot,
    OCR text, or model object reference.
    """
    if platform.system().casefold() != "windows":
        return None

    from ctypes import wintypes

    class _ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("page_fault_count", wintypes.DWORD),
            ("peak_working_set_size", ctypes.c_size_t),
            ("working_set_size", ctypes.c_size_t),
            ("quota_peak_paged_pool_usage", ctypes.c_size_t),
            ("quota_paged_pool_usage", ctypes.c_size_t),
            ("quota_peak_non_paged_pool_usage", ctypes.c_size_t),
            ("quota_non_paged_pool_usage", ctypes.c_size_t),
            ("pagefile_usage", ctypes.c_size_t),
            ("peak_pagefile_usage", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    get_current_process = kernel32.GetCurrentProcess
    get_current_process.argtypes = []
    get_current_process.restype = wintypes.HANDLE
    get_process_memory_info = psapi.GetProcessMemoryInfo
    get_process_memory_info.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_ProcessMemoryCounters),
        wintypes.DWORD,
    ]
    get_process_memory_info.restype = wintypes.BOOL

    counters = _ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    if not get_process_memory_info(get_current_process(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return {
        "working_set_bytes": int(counters.working_set_size),
        "peak_working_set_bytes": int(counters.peak_working_set_size),
        "pagefile_usage_bytes": int(counters.pagefile_usage),
        "peak_pagefile_usage_bytes": int(counters.peak_pagefile_usage),
    }


def _safe_process_memory_snapshot() -> dict[str, int] | None:
    try:
        return _process_memory_snapshot()
    except (AttributeError, OSError, TypeError, ValueError):
        return None


def _memory_delta(before: dict[str, int] | None, after: dict[str, int] | None) -> int | None:
    if before is None or after is None:
        return None
    return after["working_set_bytes"] - before["working_set_bytes"]


def _warm_latency_gate_passes(run: dict, candidate: str) -> bool:
    key = "warm_two_pass_latency_ms" if candidate == "combined_then_english" else "warm_latency_ms"
    value = run.get("ocr_window", {}).get(key)
    return isinstance(value, (int, float)) and value <= 3000


def _char_recall(expected: str, actual: str) -> float:
    expected_norm = _normalize_scored_text(expected)
    actual_norm = _normalize_scored_text(actual)
    if not expected_norm and not actual_norm:
        return 1.0
    longest = max(len(expected_norm), len(actual_norm))
    if not longest:
        return 0.0
    distance = _levenshtein_distance(expected_norm, actual_norm)
    return round(1.0 - distance / longest, 3)


def _normalize_scored_text(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value))).strip()


def _levenshtein_distance(left: str, right: str) -> int:
    if len(left) < len(right):
        left, right = right, left
    if not right:
        return len(left)
    previous = list(range(len(right) + 1))
    for left_index, left_character in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_character in enumerate(right, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + (left_character != right_character),
                )
            )
        previous = current
    return previous[-1]


def _bbox_rect(bbox: object) -> tuple[float, float, float, float] | None:
    try:
        points = list(bbox)  # type: ignore[arg-type]
        coordinates = [(float(point[0]), float(point[1])) for point in points]
    except (TypeError, ValueError, IndexError):
        return None
    if not coordinates:
        return None
    xs = [point[0] for point in coordinates]
    ys = [point[1] for point in coordinates]
    return min(xs), min(ys), max(xs), max(ys)


def _bbox_overlap_ratio(left: object, right: object) -> float:
    left_rect = _bbox_rect(left)
    right_rect = _bbox_rect(right)
    if left_rect is None or right_rect is None:
        return 0.0
    left_x1, left_y1, left_x2, left_y2 = left_rect
    right_x1, right_y1, right_x2, right_y2 = right_rect
    intersection = max(0.0, min(left_x2, right_x2) - max(left_x1, right_x1)) * max(
        0.0, min(left_y2, right_y2) - max(left_y1, right_y1)
    )
    left_area = max(0.0, left_x2 - left_x1) * max(0.0, left_y2 - left_y1)
    right_area = max(0.0, right_x2 - right_x1) * max(0.0, right_y2 - right_y1)
    smaller_area = min(left_area, right_area)
    return intersection / smaller_area if smaller_area else 0.0


def _region_confidence(region: tuple[object, object, object]) -> float:
    try:
        value = float(region[2])
    except (TypeError, ValueError):
        return 0.0
    return value if value == value and value not in (float("inf"), float("-inf")) else 0.0


def _contains_arabic(text: object) -> bool:
    return any(
        "\u0600" <= character <= "\u06ff"
        or "\u0750" <= character <= "\u077f"
        or "\u08a0" <= character <= "\u08ff"
        for character in str(text)
    )


def _merge_combined_then_english_regions(
    combined_regions: list[tuple[object, object, object]],
    english_regions: list[tuple[object, object, object]],
) -> list[tuple[object, object, object]]:
    """Merge the two fixed reader passes without adding a router or backend."""
    merged = list(combined_regions)
    for english_region in english_regions:
        overlaps = [
            (_bbox_overlap_ratio(english_region[0], existing[0]), index)
            for index, existing in enumerate(merged)
        ]
        overlap, index = max(overlaps, default=(0.0, -1))
        if overlap < 0.5 or index < 0:
            merged.append(english_region)
            continue
        existing = merged[index]
        if _contains_arabic(existing[1]):
            continue
        if _region_confidence(english_region) > _region_confidence(existing):
            merged[index] = english_region
    return merged


def _combined_quality_check(
    regions: list[tuple[object, object, object]],
) -> tuple[bool, str]:
    if not regions:
        return True, "combined_pass_empty"
    if not any(_contains_arabic(region[1]) for region in regions):
        return True, "combined_pass_missing_arabic_script"
    if not any(any("A" <= character <= "Z" or "a" <= character <= "z" for character in str(region[1])) for region in regions):
        return True, "combined_pass_missing_latin_script"
    if any(_region_confidence(region) < 0.90 for region in regions):
        return True, "combined_pass_low_confidence"
    return False, "combined_pass_acceptable"


class _CombinedThenEnglishReader:
    """Evaluation-only reader wrapper for exactly two local EasyOCR passes."""

    def __init__(self, combined_reader: object, english_factory, timing: dict[str, object]) -> None:
        self._combined_reader = combined_reader
        self._english_factory = english_factory
        self._english_reader: object | None = None
        self._timing = timing

    def readtext(self, image: object, *, detail: int = 1) -> list[tuple[object, object, object]]:
        pass_started = time.perf_counter()
        combined_regions = list(self._combined_reader.readtext(image, detail=detail))  # type: ignore[attr-defined]
        combined_latency_ms = round((time.perf_counter() - pass_started) * 1000, 1)
        run_second_pass, quality_reason = _combined_quality_check(combined_regions)
        self._timing["candidate_quality_check"] = {
            "second_pass_requested": run_second_pass,
            "reason": quality_reason,
        }
        english_regions: list[tuple[object, object, object]] = []
        english_latency_ms: float | None = None
        if self._english_reader is None:
            if run_second_pass:
                reader_started = time.perf_counter()
                self._english_reader = self._english_factory()
                self._timing["english_reader_cold_init_ms"] = round((time.perf_counter() - reader_started) * 1000, 1)
        if run_second_pass:
            started = time.perf_counter()
            english_regions = list(self._english_reader.readtext(image, detail=detail))  # type: ignore[union-attr]
            english_latency_ms = round((time.perf_counter() - started) * 1000, 1)
        records = self._timing.setdefault("candidate_pass_records", [])
        pass_count = 2 if run_second_pass else 1
        record = {
            "pass_count": pass_count,
            "passes": [{"reader": "combined_ar_en", "latency_ms": combined_latency_ms}],
            "total_pass_latency_ms": round((time.perf_counter() - pass_started) * 1000, 1),
        }
        if run_second_pass:
            record["passes"].append({"reader": "english_only", "latency_ms": english_latency_ms})
            record["total_two_pass_latency_ms"] = record["total_pass_latency_ms"]
        if isinstance(records, list):
            records.append(record)
        self._timing["reader_provenance"] = [{"reader": "combined_ar_en", "languages": ["ar", "en"]}]
        if run_second_pass:
            self._timing["reader_provenance"].append({"reader": "english_only", "languages": ["en"]})
        merged = _merge_combined_then_english_regions(combined_regions, english_regions)
        english_region_ids = {id(region) for region in english_regions}
        self._timing["last_region_sources"] = [
            "english_only" if id(region) in english_region_ids else "combined_ar_en"
            for region in merged
        ]
        return merged


def _score_expected_region(regions: list[dict], expected: str) -> dict:
    best: tuple[float, float, int, str, object] | None = None
    for index, region in enumerate(regions):
        actual = str(region.get("text", ""))
        if not actual:
            continue
        recall = _char_recall(expected, actual)
        try:
            confidence = float(region.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        candidate = (recall, confidence, -index, actual, region.get("confidence"))
        if best is None or candidate[:3] > best[:3]:
            best = candidate
    if best is None:
        return {
            "expected": expected,
            "matched_exactly": False,
            "normalized_character_recall": 0.0,
            "confidence": None,
            "actual_text": None,
        }
    return {
        "expected": expected,
        "matched_exactly": _normalize_scored_text(best[3]) == _normalize_scored_text(expected),
        "normalized_character_recall": best[0],
        "confidence": best[4],
        "actual_text": best[3],
    }


@contextlib.contextmanager
def _network_guard():
    """Scoped (not process-global) - active only around the actual
    `computer.visual.read` tool calls below, so an unrelated legitimate
    socket use elsewhere in the runtime can never produce a false
    violation."""
    original_connect = socket.socket.connect

    def _blocked_connect(self, *_args: object, **_kwargs: object) -> None:
        raise _NetworkAccessDuringOcrError("socket.connect() was called during a computer.visual.read execution - network access must be impossible")

    socket.socket.connect = _blocked_connect  # type: ignore[method-assign]
    try:
        yield
    finally:
        socket.socket.connect = original_connect  # type: ignore[method-assign]


async def _new_harness(model_dir: str):
    from jarvis.authority.identity.service import EnrollmentGrant
    from jarvis.bootstrap import create_runtime
    from jarvis.config import JarvisConfig
    from jarvis.contracts import ToolContext

    runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:", ocr_model_dir=model_dir))
    await runtime.start()
    identity = await runtime.identity.bootstrap_owner("Phase 18 OCR Acceptance Runner Owner")
    enrollment = await runtime.identity.create_enrollment(
        EnrollmentGrant(
            identity.owner_id, "Phase 18 OCR Acceptance Runner Device", "desktop", "windows",
            ("tool.request",), ("computer.observe", "computer.input"),
        )
    )
    issued = await runtime.identity.redeem_enrollment(enrollment.code)
    device = await runtime.identity.authenticate(issued.raw, issued.device_id)
    session = runtime.repository.create_session(identity.owner_id, device.device_id)
    context = ToolContext(identity, device, session.id, f"phase18-ocr-acceptance-{time.time_ns()}")
    return runtime, identity, device, context


def _configure_candidate(runtime, model_dir: str, candidate: str, timing: dict[str, object]) -> dict[str, object]:
    """Install one explicit evaluation reader behind the production adapter.

    This is runner-only configuration: Candidate A calls the accepted
    production factory, Candidate B constructs an English-only reader, and
    Candidate C composes exactly those two explicit readers for one image.
    No candidate is model- or network-routed dynamically by the product
    runtime.
    """
    candidate = _validate_candidate(candidate)
    model_error = _candidate_model_error(model_dir, candidate)
    if model_error is not None:
        raise RuntimeError(model_error)

    from jarvis.computer.visual_ocr import EasyOcrVisualAdapter

    controller = runtime.computer_actions.controller.local
    base_adapter = controller.visual_ocr_adapter
    readiness = base_adapter._models_ready()
    if readiness is not None:
        raise RuntimeError(readiness)

    model_root = Path(model_dir)

    def timed_factory(factory):
        def create_reader():
            started = time.perf_counter()
            reader = factory()
            timing["reader_cold_init_ms"] = round((time.perf_counter() - started) * 1000, 1)
            return reader

        return create_reader

    def create_english_reader():
        import easyocr

        return easyocr.Reader(
            ["en"],
            gpu=False,
            verbose=False,
            model_storage_directory=str(model_root / "model"),
            user_network_directory=str(model_root / "user_network"),
            download_enabled=False,
        )

    if candidate == "combined_ar_en":
        reader_factory = timed_factory(base_adapter._default_reader_factory)
        languages = ["ar", "en"]
    elif candidate == "english_only":
        reader_factory = timed_factory(create_english_reader)
        languages = ["en"]
    else:
        def create_combined_then_english_reader():
            return _CombinedThenEnglishReader(
                base_adapter._default_reader_factory(),
                create_english_reader,
                timing,
            )

        reader_factory = timed_factory(create_combined_then_english_reader)
        languages = [["ar", "en"], ["en"]]

    controller.visual_ocr_adapter = EasyOcrVisualAdapter(
        base_adapter.perception_provider,
        base_adapter.semantic_adapter,
        reader_factory=reader_factory,
        model_dir=model_dir,
    )
    model_metadata = _candidate_model_metadata(model_dir, candidate)
    return {
        "model_readiness_before_first_call": readiness,
        "model_files": list(_candidate_model_files(candidate)),
        "model_file_sizes": model_metadata,
        "model_footprint_bytes": sum(item["size_bytes"] for item in model_metadata),
        "reader_languages": languages,
    }


async def _find_exact_fixture_window(runtime, context, title: str) -> tuple[str | None, str | None]:
    for _ in range(20):
        await asyncio.sleep(1.0)
        listed = await runtime.tool_service.execute("computer.semantic.read", {"action": "list_windows"}, context)
        if listed.status.value != "completed":
            continue
        matches = [w for w in listed.output.get("windows", []) if w.get("title") == title]
        if len(matches) > 1:
            return None, "fixture_title_collision"
        if len(matches) == 1:
            return matches[0]["window_ref"], None
    return None, "fixture_window_not_found"


async def _find_exact_owned_fixture_window(
    runtime, context, title: str, process_id: int,
) -> tuple[str | None, str | None]:
    """Find one exact nonce title and require the runner-owned child PID.

    Window enumeration stays transient. Only the opaque window reference and
    a bounded failure reason leave this helper; the physical visual runner
    never persists a window list, title, PID, or HWND.
    """
    for _ in range(40):
        await asyncio.sleep(0.5)
        listed = await runtime.tool_service.execute(
            "computer.semantic.read", {"action": "list_windows"}, context,
        )
        if listed.status.value != "completed":
            continue
        title_matches = [w for w in listed.output.get("windows", []) if w.get("title") == title]
        if len(title_matches) > 1:
            return None, "fixture_title_collision"
        if len(title_matches) == 1:
            window_ref = title_matches[0].get("window_ref")
            provider = getattr(runtime.computer_actions.controller.local, "perception_provider", None)
            verifier = getattr(provider, "window_belongs_to_process", None)
            if not isinstance(window_ref, str) or not callable(verifier):
                return None, "fixture_process_verifier_unavailable"
            if not verifier(window_ref, process_id):
                return None, "fixture_process_verifier_failed"
            return window_ref, None
    return None, "fixture_window_not_found"


async def _wait_for_exact_fixture_absence(runtime, context, title: str) -> bool:
    """Wait for one exact nonce title to disappear after owned termination."""
    for _ in range(40):
        listed = await runtime.tool_service.execute(
            "computer.semantic.read", {"action": "list_windows"}, context,
        )
        if listed.status.value == "completed":
            if not any(w.get("title") == title for w in listed.output.get("windows", [])):
                return True
        await asyncio.sleep(0.25)
    return False


def _visual_ref_matches(regions: object, expected: str) -> list[str]:
    """Select visual refs from the current OCR result without retaining OCR.

    The text is inspected only in memory to identify the fixture-authored
    control. The returned refs are opaque and are the only values forwarded to
    `computer.visual.act`; no element lookup or geometry is involved.
    """
    if not isinstance(regions, list):
        return []
    expected_norm = _normalize_visual_target_text(expected)
    matches: list[str] = []
    for region in regions:
        if not isinstance(region, dict):
            continue
        visual_ref = region.get("visual_ref")
        text = region.get("text")
        if (
            isinstance(visual_ref, str)
            and visual_ref.startswith("visual-")
            and _normalize_visual_target_text(text or "") == expected_norm
        ):
            matches.append(visual_ref)
    return matches


def _normalize_visual_target_text(value: object) -> str:
    """Apply one fixed OCR glyph normalization for the fixture's GO label.

    This is only initial target selection; the opaque ref still binds to the
    exact production OCR digest and is re-resolved without fuzzy matching.
    """
    return _normalize_scored_text(value).casefold().replace("0", "o")


async def _status_name_present(runtime, context, window_ref: str, expected: str) -> bool:
    """Independently read one exact fixture-authored status label."""
    found = await runtime.tool_service.execute(
        "computer.semantic.read",
        {
            "action": "find_elements",
            "window_ref": window_ref,
            "control_type": "TextControl",
            "name": expected,
        },
        context,
    )
    return found.status.value == "completed" and bool(found.output.get("matches"))


async def _visual_read(runtime, context, window_ref: str):
    """Read through the production visual tool under the offline guard."""
    with _network_guard():
        return await runtime.tool_service.execute(
            "computer.visual.read", {"action": "ocr_window", "window_ref": window_ref}, context,
        )


async def _visual_request(runtime, context, visual_ref: str):
    """Issue one bounded visual action request; never retries the request."""
    with _network_guard():
        return await runtime.tool_service.execute(
            "computer.visual.act",
            {"action": "left_click_visual", "visual_ref": visual_ref},
            context,
        )


async def _visual_decide(runtime, identity, context, approval_id: str):
    """Resume one approval exactly once, under the offline guard."""
    with _network_guard():
        return await runtime.tool_service.decide_and_resume(
            approval_id, True, identity.identity_id, context,
        )


_VISUAL_PREINPUT_FOCUS_RETRIES = 2
_VISUAL_PREINPUT_FOCUS_RETRY_DELAY_SECONDS = 0.5


async def _visual_request_and_decide(runtime, identity, context, visual_ref: str):
    """Run one visual approval path with bounded pre-input focus recovery.

    Only ``window_focus_not_verified`` is retried, and every retry happens
    after an approval was consumed but before the native adapter accepted any
    input. A native injection failure or any other result returns immediately;
    this helper never retries after a move/click batch has begun.
    """
    requested = None
    decided = None
    for attempt in range(_VISUAL_PREINPUT_FOCUS_RETRIES):
        requested = await _visual_request(runtime, context, visual_ref)
        approval_id = getattr(requested, "approval_id", None)
        if _status_value(requested) != "approval_required" or not isinstance(approval_id, str):
            return requested, None
        decided = await _visual_decide(runtime, identity, context, approval_id)
        if _error_value(decided) != "window_focus_not_verified":
            return requested, decided
        if attempt + 1 < _VISUAL_PREINPUT_FOCUS_RETRIES:
            await asyncio.sleep(_VISUAL_PREINPUT_FOCUS_RETRY_DELAY_SECONDS)
    assert requested is not None
    return requested, decided


def _status_value(result: object | None) -> str | None:
    if result is None:
        return None
    status = getattr(result, "status", None)
    return getattr(status, "value", str(status)) if status is not None else None


def _error_value(result: object | None) -> str | None:
    error_code = getattr(result, "error_code", None)
    return error_code if isinstance(error_code, str) else None


def _visual_action_record(requested: object, decided: object | None = None) -> dict[str, object]:
    """Project one action to bounded statuses/reasons only."""
    record: dict[str, object] = {
        "request_status": _status_value(requested),
        "request_error_code": _error_value(requested),
        "approval_issued": _status_value(requested) == "approval_required"
        and bool(getattr(requested, "approval_id", None)),
    }
    if decided is not None:
        output = getattr(decided, "output", None)
        record.update({
            "decision_status": _status_value(decided),
            "decision_error_code": _error_value(decided),
            "delivery_reported": _status_value(decided) == "completed",
            "reported_verified": bool(getattr(decided, "verified", False)),
            "input_batch_accepted": bool(output.get("input_batch_accepted")) if isinstance(output, dict) else False,
        })
    return record


async def _find_element(runtime, context, window_ref: str, name: str) -> str | None:
    found = await runtime.tool_service.execute(
        "computer.semantic.read",
        {"action": "find_elements", "window_ref": window_ref, "control_type": "TextControl", "name": name},
        context,
    )
    if found.status.value != "completed" or not found.output.get("matches"):
        return None
    return found.output["matches"][0]["element_ref"]


async def _run_once(model_dir: str, candidate: str) -> dict:
    candidate = _validate_candidate(candidate)
    result: dict = {"attempted": True, "candidate": candidate}
    if not FIXTURE_HOST_SCRIPT.exists():
        result["attempted"] = False
        result["skip_reason"] = "fixture_host_script_missing"
        return result

    nonce = str(uuid.uuid4())
    title = f"JARVIS-CUV2-OCR-FIXTURE-{nonce}"
    runtime, identity, device, context = await _new_harness(model_dir)
    proc: subprocess.Popen | None = None
    timing: dict[str, object] = {}
    memory_before_candidate = _safe_process_memory_snapshot()
    try:
        result.update(_configure_candidate(runtime, model_dir, candidate, timing))
        result["memory_footprint"] = {
            "available": memory_before_candidate is not None,
            "before_candidate": memory_before_candidate,
            "model_footprint_bytes": result.get("model_footprint_bytes"),
        }
        proc = launch_owned_fixture(
            FIXTURE_HOST_SCRIPT,
            nonce=nonce,
        )
        window_ref, error = await _find_exact_fixture_window(runtime, context, title)
        if window_ref is None:
            result["error"] = error
            return result

        memory_before_ocr = _safe_process_memory_snapshot()
        t0 = time.perf_counter()
        with _network_guard():
            cold_read = await runtime.tool_service.execute(
                "computer.visual.read", {"action": "ocr_window", "window_ref": window_ref}, context,
            )
        cold_latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        memory_after_cold = _safe_process_memory_snapshot()
        result["memory_footprint"].update({
            "before_first_ocr": memory_before_ocr,
            "after_cold_ocr": memory_after_cold,
            "working_set_delta_after_cold_bytes": _memory_delta(memory_before_ocr, memory_after_cold),
        })
        if cold_read.status.value != "completed":
            result["ocr_window"] = {
                "status": cold_read.status.value,
                "error_code": cold_read.error_code,
                "cold_latency_ms": cold_latency_ms,
                "warm_latency_ms": None,
            }
            return result

        # The first call above includes reader construction. This second call
        # measures the normal warm path and supplies the scored observation.
        t0 = time.perf_counter()
        with _network_guard():
            window_read = await runtime.tool_service.execute(
                "computer.visual.read", {"action": "ocr_window", "window_ref": window_ref}, context,
            )
        warm_latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        memory_after_warm = _safe_process_memory_snapshot()
        result["memory_footprint"].update({
            "after_warm_ocr": memory_after_warm,
            "working_set_delta_after_warm_bytes": _memory_delta(memory_before_ocr, memory_after_warm),
        })
        window_output = window_read.output or {}
        result["ocr_window"] = {
            "status": window_read.status.value,
            "error_code": window_read.error_code,
            "reader_cold_init_ms": timing.get("reader_cold_init_ms"),
            "cold_latency_ms": cold_latency_ms,
            "warm_latency_ms": warm_latency_ms,
            "truncated": window_output.get("truncated"),
            "region_count": len(window_output.get("regions") or []),
        }
        if candidate == "combined_then_english":
            pass_records = timing.get("candidate_pass_records", [])
            first_record = pass_records[0] if isinstance(pass_records, list) and pass_records else {}
            last_record = pass_records[-1] if isinstance(pass_records, list) and pass_records else {}
            result["ocr_window"].update({
                "cold_two_pass_latency_ms": cold_latency_ms,
                "warm_two_pass_latency_ms": warm_latency_ms,
                "cold_recognition_two_pass_latency_ms": first_record.get("total_two_pass_latency_ms"),
                "warm_recognition_two_pass_latency_ms": last_record.get("total_two_pass_latency_ms"),
                "quality_check": timing.get("candidate_quality_check"),
                "reader_provenance": timing.get("reader_provenance", []),
                "pass_records": pass_records,
            })
        regions = window_output.get("regions") or []
        region_sources = timing.get("last_region_sources", [])
        result["recognized_regions"] = [
            {
                "text": region.get("text"),
                "confidence": region.get("confidence"),
                **(
                    {"source_pass": region_sources[index]}
                    if candidate == "combined_then_english"
                    and isinstance(region_sources, list)
                    and index < len(region_sources)
                    else {}
                ),
            }
            for index, region in enumerate(regions)
        ]

        for key, expected in (
            ("english_ready", LABEL_READY),
            ("arabic_greeting", LABEL_ARABIC_GREETING),
            ("arabic_settings", LABEL_ARABIC_SETTINGS),
            ("mixed_settings", LABEL_MIXED_SETTINGS),
            ("english_only", LABEL_ENGLISH_ONLY),
        ):
            result[key] = _score_expected_region(regions, expected)
        result["mixed_settings"]["arabic_substring_preserved"] = any(
            LABEL_ARABIC_SETTINGS in str(region.get("text", "")) for region in regions
        )

        # -- ocr_element cross-check: crop to just the Arabic greeting label --
        element_ref = await _find_element(runtime, context, window_ref, LABEL_ARABIC_GREETING)
        if element_ref is not None:
            t1 = time.perf_counter()
            with _network_guard():
                element_read = await runtime.tool_service.execute(
                    "computer.visual.read", {"action": "ocr_element", "element_ref": element_ref}, context,
                )
            element_latency_ms = round((time.perf_counter() - t1) * 1000, 1)
            element_output = element_read.output or {}
            element_regions = element_output.get("regions") or []
            result["ocr_element_arabic_greeting"] = {
                **_score_expected_region(element_regions, LABEL_ARABIC_GREETING),
                "status": element_read.status.value,
                "warm_latency_ms": element_latency_ms,
                "region_count": len(element_regions),
                "recognized_regions": [
                    {"text": region.get("text"), "confidence": region.get("confidence")}
                    for region in element_regions
                ],
            }
        else:
            result["ocr_element_arabic_greeting"] = {"status": "element_not_found"}

        return result
    except _NetworkAccessDuringOcrError as exc:
        result["network_violation"] = str(exc)
        return result
    finally:
        if proc is not None:
            result["fixture_child_confirmed_exited"] = terminate_owned_fixture(proc)
        await runtime.shutdown()


_VISUAL_STALE_OR_DRIFT_ERRORS = frozenset({
    "visual_ref_expired",
    "visual_ref_unknown",
    "window_ref_expired",
    "uia_window_stale",
    "visual_source_identity_changed",
    "visual_target_changed",
})


async def _run_visual_actuation_once(model_dir: str, candidate: str = "combined_ar_en") -> dict:
    """Run one clean A-E visual-actuation iteration.

    A, B, C, and D use only JARVIS's owned OCR fixture. B and D recreate the
    exact child through the allowlisted launch boundary to make the original
    opaque visual reference stale; C starts the allowlisted duplicate-target
    fixture variant. E injects failure only at the native adapter boundary so
    no real click is sent while the real visual resolver/controller path is
    still exercised.
    """
    candidate = _validate_candidate(candidate)
    result: dict[str, object] = {
        "attempted": True,
        "candidate": candidate,
        "scenarios": {},
    }
    if not FIXTURE_HOST_SCRIPT.exists():
        result["attempted"] = False
        result["skip_reason"] = "fixture_host_script_missing"
        return result

    runtime, identity, _device, context = await _new_harness(model_dir)
    active_proc: subprocess.Popen | None = None
    active_title: str | None = None

    async def _start_fixture(
        *,
        nonce: str | None = None,
        visual_variant: str | None = None,
    ) -> tuple[str | None, str, str, str | None]:
        nonlocal active_proc, active_title
        if active_proc is not None:
            raise RuntimeError("visual_fixture_already_active")
        fixture_nonce = nonce or str(uuid.uuid4())
        title = f"JARVIS-CUV2-OCR-FIXTURE-{fixture_nonce}"
        active_proc = launch_owned_fixture(
            FIXTURE_HOST_SCRIPT,
            nonce=fixture_nonce,
            visual_variant=visual_variant,
        )
        active_title = title
        window_ref, error = await _find_exact_owned_fixture_window(
            runtime, context, title, int(active_proc.pid),
        )
        if window_ref is None:
            terminate_owned_fixture(active_proc)
            await _wait_for_exact_fixture_absence(runtime, context, title)
            active_proc = None
            active_title = None
        return window_ref, fixture_nonce, title, error

    async def _stop_fixture(title: str) -> bool:
        nonlocal active_proc, active_title
        proc = active_proc
        active_proc = None
        active_title = None
        if proc is None:
            return False
        exited = terminate_owned_fixture(proc)
        absent = await _wait_for_exact_fixture_absence(runtime, context, title)
        return bool(exited and absent)

    def _read_regions(read_result: object) -> object:
        output = getattr(read_result, "output", None)
        return output.get("regions") if isinstance(output, dict) else None

    def _scenario_pass(scenario: dict[str, object]) -> bool:
        return bool(scenario.get("pass"))

    try:
        try:
            _configure_candidate(runtime, model_dir, candidate, {})
            result["configuration_ready"] = True
        except (RuntimeError, OSError, ValueError) as exc:
            result["error"] = f"visual_configuration_failed:{str(exc)[:100]}"
            return result

        scenarios = result["scenarios"]
        assert isinstance(scenarios, dict)

        # Scenario A: the only actuation target comes from computer.visual.read
        # and the effect is verified independently through the fixture status.
        a: dict[str, object] = {"observed": False, "pass": False}
        a_ref, _a_nonce, a_title, a_error = await _start_fixture()
        if a_ref is not None:
            a_read = await _visual_read(runtime, context, a_ref)
            a_matches = _visual_ref_matches(_read_regions(a_read), VISUAL_ACTION_LABEL)
            a["observed"] = _status_value(a_read) == "completed" and len(a_matches) == 1
            if len(a_matches) == 1:
                a_requested, a_decided = await _visual_request_and_decide(
                    runtime, identity, context, a_matches[0],
                )
                a.update(_visual_action_record(a_requested, a_decided))
                await asyncio.sleep(0.25)
                a["independent_status_matches_expected"] = await _status_name_present(
                    runtime, context, a_ref, VISUAL_STATUS_APPLIED,
                )
            else:
                a["request_status"] = "not_issued"
                a["request_error_code"] = "visual_action_target_not_unique"
                a["approval_issued"] = False
                a["independent_status_matches_expected"] = False
            a["pass"] = bool(
                a.get("observed")
                and a.get("approval_issued")
                and a.get("delivery_reported")
                and a.get("input_batch_accepted")
                and a.get("independent_status_matches_expected")
                and not a.get("reported_verified")
            )
        else:
            a["error"] = a_error
        a["fixture_child_confirmed_exited"] = await _stop_fixture(a_title)
        scenarios["A_happy_visual_left_click"] = a

        # Scenario B: recreate the exact owned fixture after observation and
        # send the old ref to the production resolver. A new same-title child
        # exists, but no same-text fallback is permitted.
        b: dict[str, object] = {"observed": False, "pass": False}
        b_ref, b_nonce, b_title, b_error = await _start_fixture()
        old_b_ref: str | None = None
        old_b_stopped = False
        b_cleanup = False
        if b_ref is not None:
            b_read = await _visual_read(runtime, context, b_ref)
            b_matches = _visual_ref_matches(_read_regions(b_read), VISUAL_ACTION_LABEL)
            old_b_ref = b_matches[0] if len(b_matches) == 1 else None
            b["observed"] = _status_value(b_read) == "completed" and old_b_ref is not None
            old_b_stopped = await _stop_fixture(b_title)
            b["fixture_recreated"] = False
            if old_b_stopped:
                new_b_ref, _new_b_nonce, _new_b_title, b_error = await _start_fixture(nonce=b_nonce)
                b["fixture_recreated"] = new_b_ref is not None
                if new_b_ref is not None and old_b_ref is not None:
                    b["new_fixture_status_unchanged"] = await _status_name_present(
                        runtime, context, new_b_ref, VISUAL_STATUS_READY,
                    )
                    b_requested = await _visual_request(runtime, context, old_b_ref)
                    b.update(_visual_action_record(b_requested))
                    b["stale_target_refused"] = bool(
                        _status_value(b_requested) != "approval_required"
                        and _error_value(b_requested) in _VISUAL_STALE_OR_DRIFT_ERRORS
                    )
                    b["zero_input_proven"] = bool(
                        b.get("stale_target_refused")
                        and not b.get("approval_issued")
                        and b.get("new_fixture_status_unchanged")
                    )
                b_cleanup = await _stop_fixture(_new_b_title)
        else:
            b["error"] = b_error
        b.setdefault("fixture_recreated", False)
        b.setdefault("new_fixture_status_unchanged", False)
        b.setdefault("stale_target_refused", False)
        b.setdefault("zero_input_proven", False)
        b["fixture_child_confirmed_exited"] = b_cleanup
        b["pass"] = bool(
            b.get("observed")
            and b.get("fixture_recreated")
            and b.get("stale_target_refused")
            and b.get("zero_input_proven")
        )
        scenarios["B_stale_visual_target"] = b

        # Scenario C: both duplicate OCR labels are spatially continuous with
        # the observed ref. The action must stop at ambiguity before approval.
        c: dict[str, object] = {"observed": False, "pass": False}
        c_ref, _c_nonce, c_title, c_error = await _start_fixture(
            visual_variant="duplicate_visual_target",
        )
        if c_ref is not None:
            c_read = await _visual_read(runtime, context, c_ref)
            c_matches = _visual_ref_matches(_read_regions(c_read), VISUAL_ACTION_LABEL)
            c["duplicate_visual_matches"] = len(c_matches)
            c["observed"] = _status_value(c_read) == "completed" and bool(c_matches)
            if c_matches:
                c_requested = await _visual_request(runtime, context, c_matches[0])
                c.update(_visual_action_record(c_requested))
                c["new_fixture_status_unchanged"] = await _status_name_present(
                    runtime, context, c_ref, VISUAL_STATUS_READY,
                )
                c["ambiguity_refused"] = bool(
                    _status_value(c_requested) == "denied"
                    and _error_value(c_requested) == "visual_target_ambiguous"
                )
                c["zero_input_proven"] = bool(
                    c.get("ambiguity_refused")
                    and not c.get("approval_issued")
                    and c.get("new_fixture_status_unchanged")
                )
            else:
                c["request_status"] = "not_issued"
                c["request_error_code"] = "duplicate_visual_target_not_ocr_readable"
                c["approval_issued"] = False
                c["ambiguity_refused"] = False
                c["zero_input_proven"] = False
        else:
            c["error"] = c_error
        c.setdefault("duplicate_visual_matches", 0)
        c.setdefault("new_fixture_status_unchanged", False)
        c.setdefault("ambiguity_refused", False)
        c.setdefault("zero_input_proven", False)
        c["pass"] = bool(
            c.get("observed")
            and int(c.get("duplicate_visual_matches", 0)) >= 2
            and c.get("ambiguity_refused")
            and c.get("zero_input_proven")
        )
        c["fixture_child_confirmed_exited"] = await _stop_fixture(c_title)
        scenarios["C_duplicate_visual_labels"] = c

        # Scenario D: issue approval for the old target, recreate the exact
        # same-title child before resume, and refuse without migrating refs.
        d: dict[str, object] = {"observed": False, "pass": False}
        d_ref, d_nonce, d_title, d_error = await _start_fixture()
        old_d_ref: str | None = None
        d_requested = None
        d_cleanup = False
        if d_ref is not None:
            d_read = await _visual_read(runtime, context, d_ref)
            d_matches = _visual_ref_matches(_read_regions(d_read), VISUAL_ACTION_LABEL)
            old_d_ref = d_matches[0] if len(d_matches) == 1 else None
            d["observed"] = _status_value(d_read) == "completed" and old_d_ref is not None
            if old_d_ref is not None:
                d_requested = await _visual_request(runtime, context, old_d_ref)
                d["approval_issued"] = bool(
                    _status_value(d_requested) == "approval_required"
                    and isinstance(getattr(d_requested, "approval_id", None), str)
                )
            else:
                d["approval_issued"] = False
            d_old_stopped = await _stop_fixture(d_title)
            d["fixture_recreated"] = False
            d_decided = None
            if d_old_stopped:
                new_d_ref, _new_d_nonce, new_d_title, d_error = await _start_fixture(nonce=d_nonce)
                d["fixture_recreated"] = new_d_ref is not None
                if new_d_ref is not None:
                    d["new_fixture_status_unchanged"] = await _status_name_present(
                        runtime, context, new_d_ref, VISUAL_STATUS_READY,
                    )
                if d_requested is not None and isinstance(getattr(d_requested, "approval_id", None), str):
                    d_decided = await _visual_decide(
                        runtime, identity, context, d_requested.approval_id,
                    )
                    d.update(_visual_action_record(d_requested, d_decided))
                else:
                    d.update(_visual_action_record(d_requested or object()))
                d["approval_target_drift_refused"] = bool(
                    _status_value(d_decided) == "denied"
                    and _error_value(d_decided) in _VISUAL_STALE_OR_DRIFT_ERRORS
                )
                d["no_migration_to_new_visual_ref"] = bool(
                    d.get("approval_target_drift_refused")
                    and d.get("new_fixture_status_unchanged")
                )
                d_cleanup = await _stop_fixture(new_d_title)
        else:
            d["error"] = d_error
        d.setdefault("fixture_recreated", False)
        d.setdefault("new_fixture_status_unchanged", False)
        d.setdefault("approval_target_drift_refused", False)
        d.setdefault("no_migration_to_new_visual_ref", False)
        d["fixture_child_confirmed_exited"] = d_cleanup
        d["pass"] = bool(
            d.get("observed")
            and d.get("approval_issued")
            and d.get("fixture_recreated")
            and d.get("approval_target_drift_refused")
            and d.get("no_migration_to_new_visual_ref")
        )
        scenarios["D_approval_target_drift"] = d

        # Scenario E: after the injected move batch, the click batch returns a
        # partial count. The native adapter must report uncertainty and never
        # send a second click batch.
        e: dict[str, object] = {"observed": False, "pass": False}
        e_ref, _e_nonce, e_title, e_error = await _start_fixture()
        if e_ref is not None:
            e_read = await _visual_read(runtime, context, e_ref)
            e_matches = _visual_ref_matches(_read_regions(e_read), VISUAL_ACTION_LABEL)
            e["observed"] = _status_value(e_read) == "completed" and len(e_matches) == 1
            if len(e_matches) == 1:
                from jarvis.computer.native_input import WindowsNativeInputAdapter

                controller = runtime.computer_actions.controller.local
                original_native = controller.native_input_adapter
                send_batches: list[int] = []

                class _InjectedFocusProvider:
                    """Allow E to reach the injected native boundary only.

                    The real window is still validated through the production
                    provider, but this deterministic harness does not ask the
                    host session to foreground it. Since ``send_input`` below
                    is the recording injector, this cannot send input to the
                    owner desktop while it proves the post-input failure path.
                    """

                    def __init__(self, delegate: object) -> None:
                        self._delegate = delegate

                    def validate_input_window(self, window_ref: str) -> int:
                        return self._delegate.validate_input_window(window_ref)  # type: ignore[attr-defined]

                    def focus_window(self, _window_ref: str) -> bool:
                        return True

                    def is_foreground(self, _hwnd: int) -> bool:
                        return True

                def _partial_send(inputs: object) -> int:
                    count = len(inputs)  # type: ignore[arg-type]
                    send_batches.append(count)
                    return count if count == 1 else max(0, count - 1)

                injected_native = WindowsNativeInputAdapter(
                    _InjectedFocusProvider(original_native.window_provider),  # type: ignore[arg-type]
                    original_native.semantic_adapter,
                    metrics_provider=lambda: (0, 0, 1920, 1080),
                    send_input=_partial_send,
                    get_cursor_pos=lambda: (0, 0),
                )
                controller.native_input_adapter = injected_native
                try:
                    e_requested, e_decided = await _visual_request_and_decide(
                        runtime, identity, context, e_matches[0],
                    )
                    e.update(_visual_action_record(e_requested, e_decided))
                finally:
                    controller.native_input_adapter = original_native
                e["send_input_batches"] = len(send_batches)
                e["click_batch_attempts"] = sum(1 for count in send_batches if count == 2)
                e["input_started"] = bool(send_batches)
                e["uncertain_outcome"] = bool(
                    _status_value(e_decided) == "failed"
                    and _error_value(e_decided) == "native_input_injection_failed"
                )
                e["no_automatic_second_click"] = e["click_batch_attempts"] == 1
            else:
                e["request_status"] = "not_issued"
                e["request_error_code"] = "visual_action_target_not_unique"
                e["approval_issued"] = False
                e["uncertain_outcome"] = False
                e["no_automatic_second_click"] = False
        else:
            e["error"] = e_error
        e.setdefault("send_input_batches", 0)
        e.setdefault("click_batch_attempts", 0)
        e.setdefault("input_started", False)
        e.setdefault("uncertain_outcome", False)
        e.setdefault("no_automatic_second_click", False)
        e["pass"] = bool(
            e.get("observed")
            and e.get("approval_issued")
            and e.get("input_started")
            and e.get("uncertain_outcome")
            and e.get("no_automatic_second_click")
        )
        e["fixture_child_confirmed_exited"] = await _stop_fixture(e_title)
        scenarios["E_post_input_uncertainty"] = e

        result["fixture_child_confirmed_exited"] = all(
            bool(scenario.get("fixture_child_confirmed_exited"))
            for scenario in scenarios.values()
            if isinstance(scenario, dict)
        )
        result["clean_iteration"] = bool(
            len(scenarios) == 5
            and all(_scenario_pass(scenario) for scenario in scenarios.values() if isinstance(scenario, dict))
            and result["fixture_child_confirmed_exited"]
        )
        return result
    except _NetworkAccessDuringOcrError as exc:
        result["network_violation"] = str(exc)
        result["clean_iteration"] = False
        return result
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        result["error"] = f"visual_acceptance_failed:{str(exc)[:120]}"
        result["clean_iteration"] = False
        return result
    finally:
        if active_proc is not None and active_title is not None:
            result["fixture_child_confirmed_exited"] = await _stop_fixture(active_title)
        await runtime.shutdown()


async def _visual_actuation_main(
    run_count: int, model_dir: str, candidate: str = "combined_ar_en",
) -> dict:
    """Run bounded visual A-E acceptance; callers must request exactly three."""
    candidate = _validate_candidate(candidate)
    if platform.system().casefold() != "windows":
        return {"error": "physical_acceptance_requires_windows"}
    runs = []
    for index in range(run_count):
        print(f"-- visual actuation physical acceptance run {index + 1}/{run_count} --", file=sys.stderr)
        runs.append(await _run_visual_actuation_once(model_dir, candidate))
    any_network_violation = next((r["network_violation"] for r in runs if r.get("network_violation")), None)
    scenarios = [r.get("scenarios", {}) for r in runs]

    def _count(scenario_name: str, field: str) -> int:
        return sum(
            1
            for run_scenarios in scenarios
            if isinstance(run_scenarios, dict)
            and isinstance(run_scenarios.get(scenario_name), dict)
            and bool(run_scenarios[scenario_name].get(field))
        )

    summary = {
        "mode": "visual_actuation",
        "candidate": candidate,
        "runs": len(runs),
        "network_access_ever_attempted": any_network_violation is not None,
        "network_violation_detail": any_network_violation,
        "scenario_a_click_delivery": _count("A_happy_visual_left_click", "delivery_reported"),
        "scenario_a_independent_status_matches": _count("A_happy_visual_left_click", "independent_status_matches_expected"),
        "scenario_b_stale_refused": _count("B_stale_visual_target", "stale_target_refused"),
        "scenario_b_zero_input_proven": _count("B_stale_visual_target", "zero_input_proven"),
        "scenario_c_ambiguity_refused": _count("C_duplicate_visual_labels", "ambiguity_refused"),
        "scenario_c_zero_input_proven": _count("C_duplicate_visual_labels", "zero_input_proven"),
        "scenario_d_approval_drift_refused": _count("D_approval_target_drift", "approval_target_drift_refused"),
        "scenario_d_no_migration_proven": _count("D_approval_target_drift", "no_migration_to_new_visual_ref"),
        "scenario_e_uncertain_after_input": _count("E_post_input_uncertainty", "uncertain_outcome"),
        "scenario_e_no_automatic_second_click": _count("E_post_input_uncertainty", "no_automatic_second_click"),
        "fixture_child_confirmed_exited_all": bool(runs) and all(
            bool(run.get("fixture_child_confirmed_exited")) for run in runs
        ),
        "three_clean_physical_iterations": len(runs) == 3 and all(
            bool(run.get("clean_iteration")) for run in runs
        ),
    }
    summary["verdict"] = "PASS" if summary["three_clean_physical_iterations"] else "PARTIAL"
    return {"summary": summary, "runs": runs}


async def _main(run_count: int, model_dir: str, candidate: str = "combined_ar_en") -> dict:
    candidate = _validate_candidate(candidate)
    if platform.system().casefold() != "windows":
        return {"error": "physical_acceptance_requires_windows"}
    runs = []
    for index in range(run_count):
        print(f"-- OCR physical acceptance run {index + 1}/{run_count} --", file=sys.stderr)
        runs.append(await _run_once(model_dir, candidate))
    any_network_violation = next((r["network_violation"] for r in runs if r.get("network_violation")), None)
    memory_records = [r.get("memory_footprint", {}) for r in runs]
    summary = {
        "candidate": candidate,
        "runs": len(runs),
        "network_access_ever_attempted": any_network_violation is not None,
        "network_violation_detail": any_network_violation,
        "model_footprint_bytes": next(
            (r.get("model_footprint_bytes") for r in runs if r.get("model_footprint_bytes") is not None),
            None,
        ),
        "memory_footprint_available_all": bool(runs) and all(record.get("available") for record in memory_records),
        "working_set_delta_after_cold_bytes": [
            record.get("working_set_delta_after_cold_bytes") for record in memory_records
        ],
        "working_set_delta_after_warm_bytes": [
            record.get("working_set_delta_after_warm_bytes") for record in memory_records
        ],
        "ocr_window_completed": sum(1 for r in runs if r.get("ocr_window", {}).get("status") == "completed"),
        "english_ready_matches": sum(1 for r in runs if r.get("english_ready", {}).get("matched_exactly")),
        "arabic_greeting_matches": sum(1 for r in runs if r.get("arabic_greeting", {}).get("matched_exactly")),
        "arabic_settings_matches": sum(1 for r in runs if r.get("arabic_settings", {}).get("matched_exactly")),
        "mixed_settings_matches": sum(1 for r in runs if r.get("mixed_settings", {}).get("matched_exactly")),
        "english_only_matches": sum(1 for r in runs if r.get("english_only", {}).get("matched_exactly")),
        "arabic_exact_gate_pass_runs": sum(
            1 for r in runs
            if r.get("arabic_greeting", {}).get("matched_exactly")
            and r.get("arabic_settings", {}).get("matched_exactly")
        ),
        "english_recall_gate_pass_runs": sum(
            1 for r in runs
            if all(r.get(key, {}).get("normalized_character_recall", 0.0) >= 0.90 for key in ("english_ready", "english_only"))
        ),
        "mixed_recall_gate_pass_runs": sum(
            1 for r in runs
            if r.get("mixed_settings", {}).get("normalized_character_recall", 0.0) >= 0.80
            and r.get("mixed_settings", {}).get("arabic_substring_preserved")
        ),
        "warm_latency_gate_pass_runs": sum(
            1 for r in runs if _warm_latency_gate_passes(r, candidate)
        ),
        "ocr_element_arabic_greeting_matches": sum(1 for r in runs if r.get("ocr_element_arabic_greeting", {}).get("matched_exactly")),
        "fixture_child_confirmed_exited_all": bool(runs) and all(r.get("fixture_child_confirmed_exited") for r in runs),
    }
    return {"summary": summary, "runs": runs}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--candidate", choices=OCR_CANDIDATES, default="combined_ar_en")
    parser.add_argument("--model-dir", required=True, help="Pre-provisioned offline EasyOCR model directory (see scripts/setup/provision_easyocr_models.py).")
    parser.add_argument("--out", required=True, help="UTF-8 JSON output path - results (including Arabic text) are never printed to the console.")
    parser.add_argument(
        "--visual-actuation",
        action="store_true",
        help="Run the bounded physical visual-actuation A-E scenarios against the owned OCR fixture.",
    )
    args = parser.parse_args()
    if args.visual_actuation and args.candidate != "combined_ar_en":
        parser.error("--visual-actuation requires the accepted combined_ar_en candidate")
    payload = asyncio.run(
        _visual_actuation_main(max(1, args.runs), args.model_dir, args.candidate)
        if args.visual_actuation
        else _main(max(1, args.runs), args.model_dir, args.candidate)
    )
    Path(args.out).write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"wrote {args.out}", file=sys.stderr)
    sys.exit(0 if "error" not in payload and not payload.get("summary", {}).get("network_access_ever_attempted") else 1)
