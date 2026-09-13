"""Phase 18 Workstream A Batch 06, Milestone 1 - opt-in PHYSICAL Arabic/
mixed OCR visual-grounding acceptance runner (GAP-0103).

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
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

REPO_SRC = Path(__file__).resolve().parents[2] / "src"
if str(REPO_SRC) not in sys.path:
    sys.path.insert(0, str(REPO_SRC))

FIXTURE_HOST_SCRIPT = Path(__file__).resolve().with_name("uia_ocr_fixture_host.py")

LABEL_READY = "JARVIS OCR fixture ready"
LABEL_ARABIC_GREETING = "مرحبا يا جارفيس"
LABEL_ARABIC_SETTINGS = "الإعدادات"
LABEL_MIXED_SETTINGS = "JARVIS الإعدادات"
LABEL_ENGLISH_ONLY = "JARVIS OCR FIXTURE"


class _NetworkAccessDuringOcrError(RuntimeError):
    """Raised by the network-block guard if any code reachable from a
    `computer.visual.read` call ever attempts a real socket connection -
    proves the OCR pipeline made zero network access attempts for real,
    not merely that its own offline-gate logic looks correct in isolation."""


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


def _region_text_for(regions: list[dict], expected: str) -> dict | None:
    for region in regions:
        if region.get("text", "").strip() == expected:
            return region
    return None


async def _run_once(model_dir: str) -> dict:
    result: dict = {"attempted": True}
    if not FIXTURE_HOST_SCRIPT.exists():
        result["attempted"] = False
        result["skip_reason"] = "fixture_host_script_missing"
        return result

    nonce = str(uuid.uuid4())
    title = f"JARVIS-CUV2-OCR-FIXTURE-{nonce}"
    runtime, identity, device, context = await _new_harness(model_dir)
    proc: subprocess.Popen | None = None
    try:
        proc = subprocess.Popen(
            [sys.executable, str(FIXTURE_HOST_SCRIPT), "--nonce", nonce],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
        )
        window_ref, error = await _find_exact_fixture_window(runtime, context, title)
        if window_ref is None:
            result["error"] = error
            return result

        adapter = runtime.computer_actions.controller.local.visual_ocr_adapter
        result["model_readiness_before_first_call"] = adapter._models_ready()

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
            "warm_latency_ms": warm_latency_ms,
            "truncated": window_output.get("truncated"),
            "region_count": len(window_output.get("regions") or []),
        }
        regions = window_output.get("regions") or []

        for key, expected in (
            ("english_ready", LABEL_READY),
            ("arabic_greeting", LABEL_ARABIC_GREETING),
            ("arabic_settings", LABEL_ARABIC_SETTINGS),
            ("mixed_settings", LABEL_MIXED_SETTINGS),
            ("english_only", LABEL_ENGLISH_ONLY),
        ):
            match = _region_text_for(regions, expected)
            result[key] = {
                "expected": expected,
                "matched_exactly": match is not None,
                "confidence": match.get("confidence") if match else None,
                "actual_text": (match or {}).get("text"),
            }

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
                "status": element_read.status.value,
                "warm_latency_ms": element_latency_ms,
                "matched_exactly": _region_text_for(element_regions, LABEL_ARABIC_GREETING) is not None,
                "region_count": len(element_regions),
            }
        else:
            result["ocr_element_arabic_greeting"] = {"status": "element_not_found"}

        return result
    except _NetworkAccessDuringOcrError as exc:
        result["network_violation"] = str(exc)
        return result
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            result["fixture_child_confirmed_exited"] = proc.poll() is not None
        await runtime.shutdown()


async def _main(run_count: int, model_dir: str) -> dict:
    if platform.system().casefold() != "windows":
        return {"error": "physical_acceptance_requires_windows"}
    runs = []
    for index in range(run_count):
        print(f"-- OCR physical acceptance run {index + 1}/{run_count} --", file=sys.stderr)
        runs.append(await _run_once(model_dir))
    any_network_violation = next((r["network_violation"] for r in runs if r.get("network_violation")), None)
    summary = {
        "runs": len(runs),
        "network_access_ever_attempted": any_network_violation is not None,
        "network_violation_detail": any_network_violation,
        "ocr_window_completed": sum(1 for r in runs if r.get("ocr_window", {}).get("status") == "completed"),
        "english_ready_matches": sum(1 for r in runs if r.get("english_ready", {}).get("matched_exactly")),
        "arabic_greeting_matches": sum(1 for r in runs if r.get("arabic_greeting", {}).get("matched_exactly")),
        "arabic_settings_matches": sum(1 for r in runs if r.get("arabic_settings", {}).get("matched_exactly")),
        "mixed_settings_matches": sum(1 for r in runs if r.get("mixed_settings", {}).get("matched_exactly")),
        "english_only_matches": sum(1 for r in runs if r.get("english_only", {}).get("matched_exactly")),
        "ocr_element_arabic_greeting_matches": sum(1 for r in runs if r.get("ocr_element_arabic_greeting", {}).get("matched_exactly")),
        "fixture_child_confirmed_exited_all": bool(runs) and all(r.get("fixture_child_confirmed_exited") for r in runs),
    }
    return {"summary": summary, "runs": runs}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--model-dir", required=True, help="Pre-provisioned offline EasyOCR model directory (see scripts/setup/provision_easyocr_models.py).")
    parser.add_argument("--out", required=True, help="UTF-8 JSON output path - results (including Arabic text) are never printed to the console.")
    args = parser.parse_args()
    payload = asyncio.run(_main(max(1, args.runs), args.model_dir))
    Path(args.out).write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"wrote {args.out}", file=sys.stderr)
    sys.exit(0 if "error" not in payload and not payload.get("summary", {}).get("network_access_ever_attempted") else 1)
