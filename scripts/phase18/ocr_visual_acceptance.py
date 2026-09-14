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

Batch 07's evaluation-only candidate switch is bounded to
``combined_ar_en`` (the accepted production reader) and ``english_only``
(an explicitly provisioned comparison reader). It does not alter production
configuration or create a model-driven language router:

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

OCR_CANDIDATES = ("combined_ar_en", "english_only")
CANDIDATE_MODEL_FILES = {
    "combined_ar_en": ("craft_mlt_25k.pth", "arabic.pth"),
    "english_only": ("craft_mlt_25k.pth", "english_g2.pth"),
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


def _char_recall(expected: str, actual: str) -> float:
    expected_norm = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", expected)).strip()
    actual_norm = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", actual)).strip()
    expected_chars = list(expected_norm.replace(" ", ""))
    remaining = list(actual_norm.replace(" ", ""))
    if not expected_chars:
        return 1.0
    matched = 0
    for character in expected_chars:
        if character in remaining:
            remaining.remove(character)
            matched += 1
    return round(matched / len(expected_chars), 3)


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
        "matched_exactly": best[3] == expected,
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
    production factory, while Candidate B constructs an English-only reader
    with the same explicit offline directories. No candidate is model- or
    network-routed dynamically by the product runtime.
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

    if candidate == "combined_ar_en":
        reader_factory = timed_factory(base_adapter._default_reader_factory)
        languages = ["ar", "en"]
    else:
        import easyocr

        def create_english_reader():
            return easyocr.Reader(
                ["en"],
                gpu=False,
                verbose=False,
                model_storage_directory=str(model_root / "model"),
                user_network_directory=str(model_root / "user_network"),
                download_enabled=False,
            )

        reader_factory = timed_factory(create_english_reader)
        languages = ["en"]

    controller.visual_ocr_adapter = EasyOcrVisualAdapter(
        base_adapter.perception_provider,
        base_adapter.semantic_adapter,
        reader_factory=reader_factory,
        model_dir=model_dir,
    )
    return {
        "model_readiness_before_first_call": readiness,
        "model_files": list(_candidate_model_files(candidate)),
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
    try:
        result.update(_configure_candidate(runtime, model_dir, candidate, timing))
        proc = launch_owned_fixture(
            FIXTURE_HOST_SCRIPT,
            nonce=nonce,
        )
        window_ref, error = await _find_exact_fixture_window(runtime, context, title)
        if window_ref is None:
            result["error"] = error
            return result

        t0 = time.perf_counter()
        with _network_guard():
            cold_read = await runtime.tool_service.execute(
                "computer.visual.read", {"action": "ocr_window", "window_ref": window_ref}, context,
            )
        cold_latency_ms = round((time.perf_counter() - t0) * 1000, 1)
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
        regions = window_output.get("regions") or []
        result["recognized_regions"] = [
            {"text": region.get("text"), "confidence": region.get("confidence")}
            for region in regions
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
    summary = {
        "candidate": candidate,
        "runs": len(runs),
        "network_access_ever_attempted": any_network_violation is not None,
        "network_violation_detail": any_network_violation,
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
            1 for r in runs if r.get("ocr_window", {}).get("warm_latency_ms", float("inf")) <= 3000
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
