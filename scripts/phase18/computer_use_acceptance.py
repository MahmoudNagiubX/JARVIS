"""Phase 18 Workstream A Batch 02, Milestone 2 - opt-in PHYSICAL Computer Use
V2 acceptance runner.

This is a durable development/evaluation tool, NOT part of production
`AgentRuntime` startup - it is never imported or auto-run by the product.
Run it explicitly:

    python scripts/phase18/computer_use_acceptance.py [--runs N]

Safety rules this script follows (see Batch 02 task Section 8.3, and the
Milestone 0 incident recorded in `docs/audits/PHASE_18_WORKSTREAM_A_BATCH_02.md`
Section 3.6 that motivated most of them):

- refuses to run on non-Windows;
- uses only disposable fixtures it creates itself - a fresh Calculator
  instance (only after confirming none is already running, so it can never
  attach to and disturb an owner's existing session the way the Milestone 0
  Notepad probe accidentally did) and a temporary local HTML file opened in
  a disposable Microsoft Edge **Guest** window (no owner profile, no login,
  no internet dependency);
- never enumerates or interacts with unrelated owner windows beyond what is
  needed to identify its own fixture window;
- cleans up its own processes and temp files, even on failure;
- every action goes through the real `computer.semantic.read/act`,
  `computer.pointer.act`, and `computer.keyboard.key` tools with normal
  approval - never a direct `uiautomation`/raw `SendInput` call;
- never persists raw UI text - only bounded, already-known-safe fixture
  labels this script itself created (e.g. "Seven", "Eight",
  "CalculatorResults") and structured pass/fail/verification evidence.

No retry-until-green loop: a scenario that fails is reported as failed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_SRC = Path(__file__).resolve().parents[2] / "src"
if str(REPO_SRC) not in sys.path:
    sys.path.insert(0, str(REPO_SRC))

FIXTURE_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>JARVIS Computer Use V2 Acceptance Fixture</title></head>
<body>
<button id="theButton" onclick="document.getElementById('status').innerText='button-invoked'">Invoke Me</button>
<input type="checkbox" id="theCheckbox">
<select id="theSelect"><option value="">--</option><option value="a">A</option><option value="b">B</option></select>
<div id="status">idle</div>
</body></html>
"""


def _edge_path() -> str | None:
    for candidate in (
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ):
        if Path(candidate).exists():
            return candidate
    return None


async def _new_harness():
    from jarvis.authority.identity.service import EnrollmentGrant
    from jarvis.bootstrap import create_runtime
    from jarvis.config import JarvisConfig
    from jarvis.contracts import ToolContext

    runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:"))
    await runtime.start()
    identity = await runtime.identity.bootstrap_owner("Phase 18 Acceptance Runner Owner")
    enrollment = await runtime.identity.create_enrollment(
        EnrollmentGrant(
            identity.owner_id, "Phase 18 Acceptance Runner Device", "desktop", "windows",
            ("tool.request",), ("computer.observe", "computer.input"),
        )
    )
    issued = await runtime.identity.redeem_enrollment(enrollment.code)
    device = await runtime.identity.authenticate(issued.raw, issued.device_id)
    session = runtime.repository.create_session(identity.owner_id, device.device_id)
    context = ToolContext(identity, device, session.id, f"phase18-acceptance-{time.time_ns()}")
    return runtime, identity, device, context


async def _find_own_window(runtime, context, *, matches) -> str | None:
    """Only ever returns the ref of a window matching our own fixture's
    signature - the full enumeration result is discarded immediately and
    never logged, per "never enumerate/interact with unrelated owner
    windows beyond what is necessary to identify its own fixture".

    Matching is title-based, not process-name-based: some modern in-box
    Windows apps (observed live for Calculator) are hosted by a shared
    `ApplicationFrameHost.exe` process rather than exposing their own
    process name on their top-level window, so a process-name match alone
    is unreliable here."""
    for _ in range(20):
        await asyncio.sleep(1.0)
        listed = await runtime.tool_service.execute("computer.semantic.read", {"action": "list_windows"}, context)
        if listed.status.value != "completed":
            continue
        for window in listed.output.get("windows", []):
            if matches(window):
                return window.get("window_ref")
    return None


async def _approve_and_run(runtime, identity, context, tool_name: str, arguments: dict) -> tuple[str, bool, dict]:
    requested = await runtime.tool_service.execute(tool_name, arguments, context)
    if requested.status.value != "approval_required":
        return requested.status.value, False, {}
    decided = await runtime.tool_service.decide_and_resume(requested.approval_id, True, identity.identity_id, context)
    return decided.status.value, bool(decided.verified), dict(decided.output or {})


async def _run_calculator_scenarios() -> dict:
    scenario: dict = {"fixture": "calculator", "attempted": True}
    already_running = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq CalculatorApp.exe"], capture_output=True, text=True, timeout=5, check=False,
    )
    if "CalculatorApp.exe" in (already_running.stdout or ""):
        scenario["attempted"] = False
        scenario["skip_reason"] = "calculator_already_running_skip_for_safety"
        return scenario

    runtime, identity, device, context = await _new_harness()
    proc = None
    try:
        proc = subprocess.Popen(["calc.exe"], shell=False, close_fds=True)
        window_ref = await _find_own_window(runtime, context, matches=lambda w: (w.get("title") or "").strip().casefold() == "calculator")
        if window_ref is None:
            scenario["error"] = "calculator_window_not_found"
            return scenario

        seven = await runtime.tool_service.execute(
            "computer.semantic.read",
            {"action": "find_elements", "window_ref": window_ref, "control_type": "ButtonControl", "name": "Seven"},
            context,
        )
        if seven.status.value != "completed" or not seven.output.get("matches"):
            scenario["error"] = "seven_button_not_found"
            return scenario
        seven_ref = seven.output["matches"][0]["element_ref"]

        # -- semantic invoke --
        status, verified, output = await _approve_and_run(
            runtime, identity, context, "computer.semantic.act", {"action": "invoke", "element_ref": seven_ref}
        )
        scenario["semantic_invoke"] = {"status": status, "verified": verified}

        display = await runtime.tool_service.execute(
            "computer.semantic.read",
            {"action": "find_elements", "window_ref": window_ref, "automation_id": "CalculatorResults"},
            context,
        )
        display_matches = display.output.get("matches", []) if display.status.value == "completed" else []
        scenario["semantic_invoke"]["independent_display_readback_matched_seven"] = bool(
            display_matches and display_matches[0].get("name") == "Display is 7"
        )

        # -- native left click (re-uses the same grounded element) --
        status, verified, output = await _approve_and_run(
            runtime, identity, context, "computer.pointer.act", {"action": "left_click_element", "element_ref": seven_ref}
        )
        scenario["native_left_click"] = {
            "status": status, "verified": verified,
            "pointer_target_verified": output.get("pointer_target_verified"),
            "input_batch_accepted": output.get("input_batch_accepted"),
        }

        focus_before = await runtime.tool_service.execute(
            "computer.semantic.read",
            {"action": "find_elements", "window_ref": window_ref, "control_type": "ButtonControl", "name": "Seven"},
            context,
        )
        seven_focused_before = (
            focus_before.output["matches"][0]["focused"]
            if focus_before.status.value == "completed" and focus_before.output.get("matches") else None
        )

        status, verified, output = await _approve_and_run(
            runtime, identity, context, "computer.keyboard.key", {"window_ref": window_ref, "key": "tab"}
        )
        scenario["native_key_tab"] = {"status": status}

        focus_after = await runtime.tool_service.execute(
            "computer.semantic.read",
            {"action": "find_elements", "window_ref": window_ref, "control_type": "ButtonControl", "name": "Eight"},
            context,
        )
        eight_focused_after = (
            focus_after.output["matches"][0]["focused"]
            if focus_after.status.value == "completed" and focus_after.output.get("matches") else None
        )
        scenario["native_key_tab"]["independent_focus_moved"] = bool(seven_focused_before and eight_focused_after)

        return scenario
    finally:
        if proc is not None:
            time.sleep(0.3)
            subprocess.run(["taskkill", "/IM", "CalculatorApp.exe", "/T", "/F"], capture_output=True, timeout=5, check=False)
        await runtime.shutdown()


async def _run_edge_guest_scenarios() -> dict:
    scenario: dict = {"fixture": "edge_guest_local_html", "attempted": True}
    edge_path = _edge_path()
    if edge_path is None:
        scenario["attempted"] = False
        scenario["skip_reason"] = "edge_not_found_use_another_safe_local_surface"
        return scenario

    runtime, identity, device, context = await _new_harness()
    edge_proc = None
    fixture_path = None
    try:
        fixture_fd, fixture_name = tempfile.mkstemp(suffix=".html", prefix="jarvis_phase18_acceptance_")
        fixture_path = Path(fixture_name)
        with open(fixture_fd, "w", encoding="utf-8") as handle:
            handle.write(FIXTURE_HTML)

        edge_proc = subprocess.Popen(
            [edge_path, "--guest", "--new-window", "--no-first-run", fixture_path.as_uri()],
            shell=False, close_fds=True,
        )
        window_ref = await _find_own_window(
            runtime, context,
            matches=lambda w: "jarvis computer use v2 acceptance fixture" in (w.get("title") or "").casefold(),
        )
        if window_ref is None:
            scenario["error"] = "edge_fixture_window_not_found"
            return scenario

        # Filter the button search by our own fixture's exact label - Edge's
        # own chrome (Minimize/Maximize/Close, tab-bar buttons, ...) also
        # exposes ButtonControl elements within the adapter's bounded
        # inspect depth, and a bare control_type filter would otherwise risk
        # actuating one of THOSE instead of anything belonging to our
        # fixture. Checkbox/combo have no equivalently reliable text label
        # on a bare HTML control, so those stay control_type-only - they are
        # expected to report "not_found" given the same depth limitation.
        for control_type, key, name_filter in (
            ("ButtonControl", "invoke", "Invoke Me"),
            ("CheckBoxControl", "toggle", None),
            ("ComboBoxControl", "select", None),
        ):
            find_params = {"action": "find_elements", "window_ref": window_ref, "control_type": control_type}
            if name_filter is not None:
                find_params["name"] = name_filter
            found = await runtime.tool_service.execute("computer.semantic.read", find_params, context)
            matches = found.output.get("matches", []) if found.status.value == "completed" else []
            if not matches:
                scenario[key] = {"status": "not_found", "note": "chromium_content_unreachable_at_current_inspect_depth"}
                continue
            element_ref = matches[0]["element_ref"]
            status, verified, output = await _approve_and_run(
                runtime, identity, context, "computer.semantic.act", {"action": key, "element_ref": element_ref}
            )
            scenario[key] = {"status": status, "verified": verified}

        return scenario
    finally:
        if edge_proc is not None:
            time.sleep(0.3)
            subprocess.run(["taskkill", "/PID", str(edge_proc.pid), "/T", "/F"], capture_output=True, timeout=5, check=False)
        if fixture_path is not None and fixture_path.exists():
            fixture_path.unlink()
        await runtime.shutdown()


async def _run_once() -> dict:
    return {
        "calculator": await _run_calculator_scenarios(),
        "edge_guest": await _run_edge_guest_scenarios(),
    }


def _summarize(runs: list[dict]) -> dict:
    def rate(getter):
        attempts = 0
        passes = 0
        for run in runs:
            value = getter(run)
            if value is None:
                continue
            attempts += 1
            if value:
                passes += 1
        return f"{passes}/{attempts}"

    return {
        "runs": len(runs),
        "semantic_invoke_completed": rate(lambda r: r["calculator"].get("semantic_invoke", {}).get("status") == "completed" if r["calculator"].get("attempted") else None),
        "semantic_invoke_independent_readback": rate(lambda r: r["calculator"].get("semantic_invoke", {}).get("independent_display_readback_matched_seven") if r["calculator"].get("attempted") else None),
        "native_click_pointer_verified": rate(lambda r: r["calculator"].get("native_left_click", {}).get("pointer_target_verified") if r["calculator"].get("attempted") else None),
        "native_key_focus_moved": rate(lambda r: r["calculator"].get("native_key_tab", {}).get("independent_focus_moved") if r["calculator"].get("attempted") else None),
        "edge_guest_invoke_found": rate(lambda r: r["edge_guest"].get("invoke", {}).get("status") == "completed" if r["edge_guest"].get("attempted") else None),
        "edge_guest_toggle_found": rate(lambda r: r["edge_guest"].get("toggle", {}).get("status") == "completed" if r["edge_guest"].get("attempted") else None),
        "edge_guest_select_found": rate(lambda r: r["edge_guest"].get("select", {}).get("status") == "completed" if r["edge_guest"].get("attempted") else None),
    }


async def _main(run_count: int) -> int:
    if platform.system().casefold() != "windows":
        print(json.dumps({"error": "physical_acceptance_requires_windows"}))
        return 1
    runs = []
    for index in range(run_count):
        print(f"-- physical acceptance run {index + 1}/{run_count} --", file=sys.stderr)
        runs.append(await _run_once())
    summary = _summarize(runs)
    print(json.dumps({"summary": summary, "runs": runs}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()
    sys.exit(asyncio.run(_main(max(1, args.runs))))
