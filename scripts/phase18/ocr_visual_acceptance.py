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
    args = parser.parse_args()
    payload = asyncio.run(_main(max(1, args.runs), args.model_dir, args.candidate))
    Path(args.out).write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"wrote {args.out}", file=sys.stderr)
    sys.exit(0 if "error" not in payload and not payload.get("summary", {}).get("network_access_ever_attempted") else 1)
