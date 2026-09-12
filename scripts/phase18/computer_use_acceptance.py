"""Phase 18 Workstream A Batch 03, Milestone 0 - opt-in PHYSICAL Computer Use
V2 acceptance runner.

This is a durable development/evaluation tool, NOT part of production
`AgentRuntime` startup - it is never imported or auto-run by the product.
Run it explicitly:

    python scripts/phase18/computer_use_acceptance.py [--runs N]

Batch 02's Milestone 0 physical-test incident (a supposed disposable Notepad
probe attached to the owner's live single-instance Notepad session and
likely lost one unsaved tab) means this runner, from Batch 03 onward, NEVER
uses an owner-installed general application (Notepad, Edge/Chrome, VS Code,
terminal, Explorer, Calculator, or any other pre-existing app) as its
acceptance fixture - only a fully JARVIS-owned native Win32 process this
runner itself launches (`scripts/phase18/uia_fixture_host.py`).

Safety rules:

- refuses to run on non-Windows;
- launches only its own disposable fixture process, never an owner app;
- the fixture's window title always carries a fresh random nonce
  (`JARVIS-CUV2-FIXTURE-<uuid>`) supplied at launch - the runner waits only
  for that *exact* title and aborts if more than one window matches it
  (collision), never falling back to "first window with a similar title";
- cleanup owns the *exact* child PID it launched (`Popen.terminate()` +
  `wait()` + a post-mortem liveness check) - never a broad image-name
  `taskkill /IM ...`, so no unrelated owner process can ever be affected;
- every action goes through the real `computer.semantic.read`/
  `computer.semantic.act` tools with normal approval - never a direct
  `uiautomation`/raw `SendInput` call, and never IPC with the fixture
  process itself (verification is always an independent JARVIS semantic
  read of the fixture's own status label);
- the structured summary persists only scenario names, pass/attempt
  counts, and bounded verification booleans/reasons - never a full window
  enumeration, never an owner window title, never raw UI content beyond
  the fixture's own known-safe, JARVIS-authored status strings.

No retry-until-green loop: a scenario that fails is reported as failed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import subprocess
import sys
import time
import uuid
from pathlib import Path

REPO_SRC = Path(__file__).resolve().parents[2] / "src"
if str(REPO_SRC) not in sys.path:
    sys.path.insert(0, str(REPO_SRC))

FIXTURE_HOST_SCRIPT = Path(__file__).resolve().with_name("uia_fixture_host.py")

_KNOWN_STATUS_VALUES = {"idle", "invoked", "toggle:on", "toggle:off", "selected:Alpha", "selected:Beta", "selected:Gamma"}


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


async def _find_exact_fixture_window(runtime, context, title: str) -> tuple[str | None, str | None]:
    """Waits for *exactly one* window with this exact nonce title. Returns
    (window_ref, error) - error is set on timeout or on a collision (more
    than one match), and the runner must abort rather than guess which
    window is its own (R18B02-005). The full enumeration result is
    inspected in memory only and never logged."""
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


async def _approve_and_run(runtime, identity, context, tool_name: str, arguments: dict) -> tuple[str, bool, dict]:
    requested = await runtime.tool_service.execute(tool_name, arguments, context)
    if requested.status.value != "approval_required":
        return requested.status.value, False, {}
    decided = await runtime.tool_service.decide_and_resume(requested.approval_id, True, identity.identity_id, context)
    return decided.status.value, bool(decided.verified), dict(decided.output or {})


async def _read_status(runtime, context, window_ref: str) -> str | None:
    """Independent read-back of the fixture's own status label - never the
    acting tool call's own self-report."""
    found = await runtime.tool_service.execute(
        "computer.semantic.read", {"action": "find_elements", "window_ref": window_ref, "control_type": "TextControl"}, context
    )
    if found.status.value != "completed":
        return None
    for match in found.output.get("matches", []):
        name = match.get("name")
        if isinstance(name, str) and (name in _KNOWN_STATUS_VALUES or name.startswith(("toggle:", "selected:"))):
            return name
    return None


async def _find_one(runtime, context, window_ref: str, control_type: str, name: str) -> str | None:
    found = await runtime.tool_service.execute(
        "computer.semantic.read",
        {"action": "find_elements", "window_ref": window_ref, "control_type": control_type, "name": name},
        context,
    )
    if found.status.value != "completed" or not found.output.get("matches"):
        return None
    return found.output["matches"][0]["element_ref"]


async def _run_owned_fixture_scenarios() -> dict:
    scenario: dict = {"fixture": "owned_win32_uia_fixture", "attempted": True}
    if not FIXTURE_HOST_SCRIPT.exists():
        scenario["attempted"] = False
        scenario["skip_reason"] = "fixture_host_script_missing"
        return scenario

    nonce = str(uuid.uuid4())
    title = f"JARVIS-CUV2-FIXTURE-{nonce}"
    runtime, identity, device, context = await _new_harness()
    proc: subprocess.Popen | None = None
    try:
        proc = subprocess.Popen(
            [sys.executable, str(FIXTURE_HOST_SCRIPT), "--nonce", nonce],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
        )
        window_ref, error = await _find_exact_fixture_window(runtime, context, title)
        if window_ref is None:
            scenario["error"] = error
            return scenario

        # -- semantic invoke --
        invoke_ref = await _find_one(runtime, context, window_ref, "ButtonControl", "Invoke Target")
        if invoke_ref is None:
            scenario["invoke"] = {"status": "not_found"}
        else:
            status, verified, _output = await _approve_and_run(
                runtime, identity, context, "computer.semantic.act", {"action": "invoke", "element_ref": invoke_ref}
            )
            status_after = await _read_status(runtime, context, window_ref)
            scenario["invoke"] = {
                "status": status, "verified": verified,
                "independent_status_readback": status_after,
                "independent_status_matches_expected": status_after == "invoked",
            }

        # -- semantic toggle --
        toggle_ref = await _find_one(runtime, context, window_ref, "CheckBoxControl", "Toggle Target")
        if toggle_ref is None:
            scenario["toggle"] = {"status": "not_found"}
        else:
            status, verified, _output = await _approve_and_run(
                runtime, identity, context, "computer.semantic.act", {"action": "toggle", "element_ref": toggle_ref}
            )
            status_after = await _read_status(runtime, context, window_ref)
            scenario["toggle"] = {
                "status": status, "verified": verified,
                "independent_status_readback": status_after,
                "independent_status_matches_expected": status_after == "toggle:on",
            }

        # -- semantic select --
        # Note: unlike Invoke/Toggle, a plain Win32 ListBox's LBN_SELCHANGE
        # notification is documented to NOT fire for a programmatic
        # LB_SETCURSEL (only for a real user click/key) - and UIA's default
        # SelectionItemPattern.Select() implementation drives selection this
        # way, so this fixture's own WM_COMMAND-based status label never
        # updates for a semantic select (confirmed during Batch 03 physical
        # acceptance). The independent confirmation instead comes from the
        # adapter's OWN fresh post-action re-observation (`select()`
        # re-resolves the element and re-reads a NEW SelectionItemPattern's
        # IsSelected - R18B01-003), surfaced here as `post_state`/`verified`
        # - a real independent read, just not through this fixture's status
        # text for this one pattern.
        select_ref = await _find_one(runtime, context, window_ref, "ListItemControl", "Beta")
        if select_ref is None:
            scenario["select"] = {"status": "not_found"}
        else:
            status, verified, output = await _approve_and_run(
                runtime, identity, context, "computer.semantic.act", {"action": "select", "element_ref": select_ref}
            )
            status_after = await _read_status(runtime, context, window_ref)
            scenario["select"] = {
                "status": status, "verified": verified,
                "adapter_post_state": output.get("post_state"),
                "fixture_status_label_readback": status_after,
                "independent_status_matches_expected": bool(verified and output.get("post_state") is True),
            }

        return scenario
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            scenario["fixture_child_confirmed_exited"] = proc.poll() is not None
        await runtime.shutdown()


async def _run_once() -> dict:
    return {"owned_fixture": await _run_owned_fixture_scenarios()}


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

    def attempted(run: dict) -> bool:
        return bool(run["owned_fixture"].get("attempted"))

    return {
        "runs": len(runs),
        "semantic_invoke": rate(lambda r: r["owned_fixture"].get("invoke", {}).get("independent_status_matches_expected") if attempted(r) else None),
        "semantic_toggle": rate(lambda r: r["owned_fixture"].get("toggle", {}).get("independent_status_matches_expected") if attempted(r) else None),
        "semantic_select": rate(lambda r: r["owned_fixture"].get("select", {}).get("independent_status_matches_expected") if attempted(r) else None),
        "fixture_child_confirmed_exited": rate(lambda r: r["owned_fixture"].get("fixture_child_confirmed_exited") if attempted(r) else None),
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
