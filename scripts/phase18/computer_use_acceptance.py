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
TEXT_FIXTURE_HOST_SCRIPT = Path(__file__).resolve().with_name("uia_text_fixture_host.py")
RECOVERY_FIXTURE_HOST_SCRIPT = Path(__file__).resolve().with_name("uia_recovery_fixture_host.py")

_KNOWN_STATUS_VALUES = {"idle", "invoked", "toggle:on", "toggle:off", "selected:Alpha", "selected:Beta", "selected:Gamma"}
_KNOWN_TEXT_FIXTURE_STATUS_VALUES = {"idle", "drag:accepted", "drag:rejected"}
ARABIC_FIXTURE_PHRASE = "مرحبا يا جارفيس"
ENGLISH_FIXTURE_PHRASE = "JARVIS COMPUTER USE"
CLIPBOARD_SENTINEL = "jarvis-fixture-clipboard-sentinel"


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


# Windows' SetForegroundWindow foreground-activation gate is time/input-
# history sensitive: a background process (this runner) can be denied
# foreground activation for a freshly created window depending on exactly
# when the OS considers the calling process/thread to hold "recent input"
# standing - a well-documented OS-level race, not a JARVIS or fixture
# defect. This retries only the mechanical foreground precondition (never
# the semantic outcome of the action itself) a bounded few times with a
# short delay - never disguising a real functional failure, since the FINAL
# reported status/attempt count is always the true last outcome.
_FOREGROUND_RETRY_ATTEMPTS = 4
_FOREGROUND_RETRY_DELAY_SECONDS = 0.75


async def _approve_and_run(runtime, identity, context, tool_name: str, arguments: dict) -> tuple[str, bool, dict]:
    last_status, last_verified, last_output = "denied", False, {}
    for attempt in range(_FOREGROUND_RETRY_ATTEMPTS):
        requested = await runtime.tool_service.execute(tool_name, arguments, context)
        if requested.status.value != "approval_required":
            return requested.status.value, False, {}
        decided = await runtime.tool_service.decide_and_resume(requested.approval_id, True, identity.identity_id, context)
        last_status, last_verified, last_output = decided.status.value, bool(decided.verified), dict(decided.output or {})
        if decided.error_code != "window_focus_not_verified":
            return last_status, last_verified, last_output
        if attempt + 1 < _FOREGROUND_RETRY_ATTEMPTS:
            print(f"   (foreground activation denied, retrying {tool_name} {arguments.get('action') or arguments.get('key') or arguments.get('chord') or ''} - attempt {attempt + 2}/{_FOREGROUND_RETRY_ATTEMPTS})", file=sys.stderr)
            await asyncio.sleep(_FOREGROUND_RETRY_DELAY_SECONDS)
    return last_status, last_verified, last_output


async def _read_status(runtime, context, window_ref: str, known_values: set[str] = _KNOWN_STATUS_VALUES) -> str | None:
    """Independent read-back of the fixture's own status label - never the
    acting tool call's own self-report."""
    found = await runtime.tool_service.execute(
        "computer.semantic.read", {"action": "find_elements", "window_ref": window_ref, "control_type": "TextControl"}, context
    )
    if found.status.value != "completed":
        return None
    for match in found.output.get("matches", []):
        name = match.get("name")
        if isinstance(name, str) and (name in known_values or name.startswith(("toggle:", "selected:", "drag:"))):
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

        # -- native left click (re-uses "Invoke Target" - independent
        # status read-back proves the real physical click landed) --
        if invoke_ref is not None:
            status, verified, output = await _approve_and_run(
                runtime, identity, context, "computer.pointer.act", {"action": "left_click_element", "element_ref": invoke_ref}
            )
            status_after = await _read_status(runtime, context, window_ref)
            scenario["native_left_click"] = {
                "status": status, "verified": verified,
                "pointer_target_verified": output.get("pointer_target_verified"),
                "independent_status_matches_expected": status_after == "invoked",
            }

            # -- native right click (delivery evidence only - a standard
            # Win32 button does not react to a right click, so no status
            # change is expected; never assume a context menu opened) --
            status, verified, output = await _approve_and_run(
                runtime, identity, context, "computer.pointer.act", {"action": "right_click_element", "element_ref": invoke_ref}
            )
            scenario["native_right_click"] = {"status": status, "verified": verified, "input_batch_accepted": output.get("input_batch_accepted")}

            # -- native double click (both individual clicks re-fire
            # BN_CLICKED on the same button - independent status read-back
            # still proves delivery + effect) --
            status, verified, output = await _approve_and_run(
                runtime, identity, context, "computer.pointer.act", {"action": "double_click_element", "element_ref": invoke_ref}
            )
            status_after = await _read_status(runtime, context, window_ref)
            scenario["native_double_click"] = {
                "status": status, "verified": verified,
                "independent_status_matches_expected": status_after == "invoked",
            }

            # -- native scroll (delivery evidence only over the list box -
            # no generic "content changed" claim) --
            status, verified, output = await _approve_and_run(
                runtime, identity, context, "computer.pointer.act",
                {"action": "scroll_element", "element_ref": invoke_ref, "direction": "down", "steps": 1},
            )
            scenario["native_scroll"] = {"status": status, "verified": verified, "input_batch_accepted": output.get("input_batch_accepted")}

        # -- native Tab key (independent focus read-back: Invoke Target has
        # focus from the clicks above, Tab should move it to Toggle Target) --
        status, verified, output = await _approve_and_run(
            runtime, identity, context, "computer.keyboard.key", {"window_ref": window_ref, "key": "tab"}
        )
        toggle_focus_check = await runtime.tool_service.execute(
            "computer.semantic.read",
            {"action": "find_elements", "window_ref": window_ref, "control_type": "CheckBoxControl", "name": "Toggle Target"},
            context,
        )
        toggle_focused = bool(
            toggle_focus_check.status.value == "completed"
            and toggle_focus_check.output.get("matches")
            and toggle_focus_check.output["matches"][0].get("focused")
        )
        scenario["native_key_tab"] = {"status": status, "independent_focus_moved": toggle_focused}

        # -- native chord (delivery evidence only - Ctrl+C over a window
        # with no text selection has no observable effect on this fixture) --
        status, verified, output = await _approve_and_run(
            runtime, identity, context, "computer.keyboard.chord", {"window_ref": window_ref, "chord": "ctrl+c"}
        )
        scenario["native_chord"] = {"status": status, "verified": verified}

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


async def _run_text_drag_fixture_scenarios() -> dict:
    """Second owned fixture (Batch 04 Milestone 1) - grounded drag and
    literal-typing (English + Arabic Unicode) physical acceptance. Same
    safety discipline as `_run_owned_fixture_scenarios`: exact-nonce-title
    matching, exact-PID cleanup, real tool calls with normal approval, no
    IPC with the fixture process, no owner clipboard content ever read or
    logged - a known sentinel is written first, then restored at the end."""
    scenario: dict = {"fixture": "owned_win32_text_drag_fixture", "attempted": True}
    if not TEXT_FIXTURE_HOST_SCRIPT.exists():
        scenario["attempted"] = False
        scenario["skip_reason"] = "text_fixture_host_script_missing"
        return scenario

    nonce = str(uuid.uuid4())
    title = f"JARVIS-CUV2-TEXT-FIXTURE-{nonce}"
    runtime, identity, device, context = await _new_harness()
    proc: subprocess.Popen | None = None
    try:
        proc = subprocess.Popen(
            [sys.executable, str(TEXT_FIXTURE_HOST_SCRIPT), "--nonce", nonce],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
        )
        window_ref, error = await _find_exact_fixture_window(runtime, context, title)
        if window_ref is None:
            scenario["error"] = error
            return scenario

        async def _edit_ref() -> str | None:
            found = await runtime.tool_service.execute(
                "computer.semantic.read", {"action": "find_elements", "window_ref": window_ref, "control_type": "EditControl"}, context
            )
            if found.status.value != "completed" or not found.output.get("matches"):
                return None
            return found.output["matches"][0]["element_ref"]

        async def _read_edit_text() -> str | None:
            ref = await _edit_ref()
            if ref is None:
                return None
            read = await runtime.tool_service.execute("computer.semantic.read", {"action": "get_text", "element_ref": ref}, context)
            return read.output.get("text") if read.status.value == "completed" else None

        # -- drag: source -> target, independent status read-back --
        source_ref = await _find_one(runtime, context, window_ref, "ButtonControl", "Drag Source")
        target_ref = await _find_one(runtime, context, window_ref, "ButtonControl", "Drop Target")
        if source_ref is None or target_ref is None:
            scenario["drag"] = {"status": "not_found"}
        else:
            status, verified, output = await _approve_and_run(
                runtime, identity, context, "computer.pointer.act",
                {"action": "drag_element_to_element", "source_element_ref": source_ref, "target_element_ref": target_ref},
            )
            status_after = await _read_status(runtime, context, window_ref, _KNOWN_TEXT_FIXTURE_STATUS_VALUES)
            scenario["drag"] = {
                "status": status, "verified": verified,
                "pointer_target_verified": output.get("pointer_target_verified"),
                "independent_status_readback": status_after,
                "independent_status_matches_expected": status_after == "drag:accepted",
            }

        # -- literal English typing (select-all then type replaces content) --
        status, _verified, _output = await _approve_and_run(
            runtime, identity, context, "computer.keyboard.chord", {"window_ref": window_ref, "chord": "ctrl+a"}
        )
        english_ref = await _edit_ref()
        if english_ref is not None:
            status, _verified, output = await _approve_and_run(
                runtime, identity, context, "computer.keyboard.type", {"window_ref": window_ref, "text": ENGLISH_FIXTURE_PHRASE}
            )
            text_after = await _read_edit_text()
            scenario["literal_typing_english"] = {
                "status": status, "chars_sent": output.get("chars_sent"),
                "independent_text_readback_matches_expected": text_after == ENGLISH_FIXTURE_PHRASE,
            }
        else:
            scenario["literal_typing_english"] = {"status": "not_found"}

        # -- literal Arabic Unicode typing (select-all then type replaces
        # content again) - existing literal typing path is not modified for
        # this, only exercised with non-ASCII text --
        await _approve_and_run(runtime, identity, context, "computer.keyboard.chord", {"window_ref": window_ref, "chord": "ctrl+a"})
        status, _verified, output = await _approve_and_run(
            runtime, identity, context, "computer.keyboard.type", {"window_ref": window_ref, "text": ARABIC_FIXTURE_PHRASE}
        )
        text_after = await _read_edit_text()
        scenario["literal_typing_arabic"] = {
            "status": status, "chars_sent": output.get("chars_sent"),
            "independent_text_readback_matches_expected": text_after == ARABIC_FIXTURE_PHRASE,
            "independent_text_readback": text_after,
        }

        # -- Home/End: prove cursor movement via prepend/append markers
        # around the Arabic phrase currently in the field --
        await _approve_and_run(runtime, identity, context, "computer.keyboard.key", {"window_ref": window_ref, "key": "home"})
        await _approve_and_run(runtime, identity, context, "computer.keyboard.type", {"window_ref": window_ref, "text": "H"})
        after_home = await _read_edit_text()
        await _approve_and_run(runtime, identity, context, "computer.keyboard.key", {"window_ref": window_ref, "key": "end"})
        await _approve_and_run(runtime, identity, context, "computer.keyboard.type", {"window_ref": window_ref, "text": "E"})
        after_end = await _read_edit_text()
        expected_after_home = "H" + ARABIC_FIXTURE_PHRASE
        scenario["native_key_home_end"] = {
            "home_marker_prepended": after_home == expected_after_home,
            "end_marker_appended": after_end == (expected_after_home + "E") if after_home == expected_after_home else False,
            "independent_text_readback": after_end,
        }

        # -- Backspace: one character shorter after one press at the end --
        before_len = len(after_end) if isinstance(after_end, str) else None
        await _approve_and_run(runtime, identity, context, "computer.keyboard.key", {"window_ref": window_ref, "key": "backspace"})
        after_backspace = await _read_edit_text()
        scenario["native_key_backspace"] = {
            "one_character_shorter": (
                isinstance(after_backspace, str) and before_len is not None and len(after_backspace) == before_len - 1
            ),
            "independent_text_readback": after_backspace,
        }

        # -- ctrl+a / ctrl+c clipboard round-trip: write a known sentinel
        # FIRST (never inspect whatever the owner's clipboard already held),
        # select the fixture's own known text, copy it, then independently
        # read back the clipboard and confirm it now holds the fixture text
        # rather than the sentinel - proving ctrl+c actually changed it. --
        await _approve_and_run(runtime, identity, context, "computer.clipboard.write", {"text": CLIPBOARD_SENTINEL})
        known_text = await _read_edit_text()
        await _approve_and_run(runtime, identity, context, "computer.keyboard.chord", {"window_ref": window_ref, "chord": "ctrl+a"})
        status, _verified, _output = await _approve_and_run(
            runtime, identity, context, "computer.keyboard.chord", {"window_ref": window_ref, "chord": "ctrl+c"}
        )
        clip_read = await runtime.tool_service.execute("computer.clipboard.read", {}, context)
        clip_text = clip_read.output.get("text") if clip_read.status.value == "completed" else None
        scenario["native_chord_ctrl_c"] = {
            "status": status,
            "clipboard_now_holds_fixture_text": bool(known_text is not None and clip_text == known_text),
        }
        # Restore fixture-created clipboard content to the harmless sentinel
        # rather than leaving the fixture's text sitting in the owner's
        # clipboard.
        await _approve_and_run(runtime, identity, context, "computer.clipboard.write", {"text": CLIPBOARD_SENTINEL})

        # -- ctrl+z: undo the most recent edit (Backspace above) --
        before_undo = after_backspace
        status, _verified, _output = await _approve_and_run(
            runtime, identity, context, "computer.keyboard.chord", {"window_ref": window_ref, "chord": "ctrl+z"}
        )
        after_undo = await _read_edit_text()
        scenario["native_chord_ctrl_z"] = {
            "status": status,
            "independent_text_changed_from_pre_undo_state": after_undo != before_undo,
            "independent_text_readback": after_undo,
        }

        # -- Tab: focus moves from the Edit control to Drag Source. Runs
        # LAST among the text-fixture keyboard scenarios - it deliberately
        # moves focus away from the Edit control, which would otherwise
        # break every later Edit-control-targeted test that follows it
        # (found during physical dogfooding: with Tab run earlier, the
        # ctrl+a/ctrl+c/ctrl+z chords that came after it landed on the
        # "Drag Source" button instead of the Edit control and did
        # nothing). --
        status, _verified, _output = await _approve_and_run(
            runtime, identity, context, "computer.keyboard.key", {"window_ref": window_ref, "key": "tab"}
        )
        source_focus_check = await runtime.tool_service.execute(
            "computer.semantic.read",
            {"action": "find_elements", "window_ref": window_ref, "control_type": "ButtonControl", "name": "Drag Source"},
            context,
        )
        source_focused = bool(
            source_focus_check.status.value == "completed"
            and source_focus_check.output.get("matches")
            and source_focus_check.output["matches"][0].get("focused")
        )
        scenario["native_key_tab"] = {"status": status, "independent_focus_moved": source_focused}

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


async def _run_recovery_fixture_scenarios() -> dict:
    """Batch 06 Milestone 2 (GAP-0104) - physical bounded-recovery
    acceptance against a third owned fixture that accepts a small,
    deterministic MOVE/REPLACE command channel over its own stdin (see
    `uia_recovery_fixture_host.py`'s own docstring for the full safety
    rationale). Every command's effect is confirmed independently via a
    real `computer.semantic.read` call before the runner proceeds to the
    actual JARVIS action under test - no uncontrolled process racing, and
    the fixture's own status label is never treated as proof of what
    JARVIS itself did, only of what the fixture itself changed.

    Two scenarios only, deliberately - both fully sequential, zero-race:
    a successful recovery cycle and a budget-exhaustion cycle both require
    landing a JARVIS action's *internal* grounding calls inside a
    millisecond-scale window relative to a fixture-side state change,
    which cannot be done deterministically from an external process; those
    contracts remain proven by the deterministic `RecoveryTests`/
    `RecoveryBudgetScopeTests` suites (Batch 05/06 Milestone 0) and the
    `computer_use_v2` evaluation-suite cases instead, per the task's own
    allowance to retain deterministic injection for scenarios that are
    unsafe or impossible to produce physically without ambiguity."""
    scenario: dict = {"fixture": "owned_win32_recovery_fixture", "attempted": True}
    if not RECOVERY_FIXTURE_HOST_SCRIPT.exists():
        scenario["attempted"] = False
        scenario["skip_reason"] = "recovery_fixture_host_script_missing"
        return scenario

    nonce = str(uuid.uuid4())
    title = f"JARVIS-CUV2-RECOVERY-FIXTURE-{nonce}"
    runtime, identity, device, context = await _new_harness()
    proc: subprocess.Popen | None = None
    try:
        proc = subprocess.Popen(
            [sys.executable, str(RECOVERY_FIXTURE_HOST_SCRIPT), "--nonce", nonce],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, text=True,
        )
        window_ref, error = await _find_exact_fixture_window(runtime, context, title)
        if window_ref is None:
            scenario["error"] = error
            return scenario

        async def _find_target_ref() -> str | None:
            found = await runtime.tool_service.execute(
                "computer.semantic.read",
                {"action": "find_elements", "window_ref": window_ref, "control_type": "ButtonControl", "name": "Recovery Target"},
                context,
            )
            if found.status.value != "completed" or not found.output.get("matches"):
                return None
            return found.output["matches"][0]["element_ref"]

        async def _read_status() -> str | None:
            found = await runtime.tool_service.execute(
                "computer.semantic.read", {"action": "find_elements", "window_ref": window_ref, "control_type": "TextControl"}, context,
            )
            if found.status.value != "completed":
                return None
            for match in found.output.get("matches", []):
                name = match.get("name")
                if isinstance(name, str) and (name.startswith("ready:") or name.startswith("clicked:")):
                    return name
            return None

        def _send(command: str) -> None:
            assert proc is not None and proc.stdin is not None
            proc.stdin.write(command + "\n")
            proc.stdin.flush()

        # -- scenario A: relocation before input - same identity preserved,
        # fresh bounds used before execution, one action delivery maximum --
        ref_a = await _find_target_ref()
        if ref_a is None:
            scenario["relocation_before_input"] = {"status": "target_not_found"}
        else:
            before = await runtime.tool_service.execute("computer.semantic.read", {"action": "get_element", "element_ref": ref_a}, context)
            bounds_before = (before.output or {}).get("element", {}).get("bounds") if before.status.value == "completed" else None
            _send("MOVE")
            bounds_after, same_ref_valid = bounds_before, False
            for _ in range(10):
                await asyncio.sleep(0.3)
                after = await runtime.tool_service.execute("computer.semantic.read", {"action": "get_element", "element_ref": ref_a}, context)
                same_ref_valid = after.status.value == "completed"
                bounds_after = (after.output or {}).get("element", {}).get("bounds") if same_ref_valid else None
                if bounds_after is not None and bounds_after != bounds_before:
                    break
            status, _verified, _output = await _approve_and_run(
                runtime, identity, context, "computer.pointer.act", {"action": "left_click_element", "element_ref": ref_a}
            )
            status_after = await _read_status()
            scenario["relocation_before_input"] = {
                "status": status,
                "same_ref_still_valid_after_move": same_ref_valid,
                "bounds_changed": bounds_after != bounds_before,
                "independent_status_readback": status_after,
                "click_landed_on_same_generation": status_after == "clicked:gen0",
            }

        # -- scenario B: approval identity change - target replaced with a
        # different strong identity (destroy+recreate -> new RuntimeId)
        # after the approval request but before decide; the existing
        # approval must be refused, zero input delivered, no recovery
        # leniency at the approval layer --
        ref_b = await _find_target_ref()
        if ref_b is None:
            scenario["approval_identity_change"] = {"status": "target_not_found"}
        else:
            requested = await runtime.tool_service.execute(
                "computer.pointer.act", {"action": "left_click_element", "element_ref": ref_b}, context
            )
            if requested.status.value != "approval_required" or requested.approval_id is None:
                scenario["approval_identity_change"] = {"status": "unexpected_request_status", "detail": requested.status.value}
            else:
                _send("REPLACE")
                stale_confirmed = False
                for _ in range(10):
                    await asyncio.sleep(0.3)
                    check = await runtime.tool_service.execute("computer.semantic.read", {"action": "get_element", "element_ref": ref_b}, context)
                    if check.status.value == "failed" and check.error_code == "uia_element_stale":
                        stale_confirmed = True
                        break
                decided = await runtime.tool_service.decide_and_resume(requested.approval_id, True, identity.identity_id, context)
                status_after = await _read_status()
                scenario["approval_identity_change"] = {
                    "old_ref_confirmed_stale_before_decide": stale_confirmed,
                    "decide_status": decided.status.value,
                    "decide_error_code": decided.error_code,
                    "refused_before_any_input": decided.status.value == "denied",
                    "independent_status_readback": status_after,
                    "zero_input_delivered": status_after is not None and not status_after.startswith("clicked:"),
                }

        return scenario
    finally:
        if proc is not None:
            if proc.stdin is not None:
                try:
                    proc.stdin.close()
                except OSError:
                    pass
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            scenario["fixture_child_confirmed_exited"] = proc.poll() is not None
        await runtime.shutdown()


def _virtual_desktop_metrics() -> tuple[int, int, int, int, int]:
    import ctypes
    user32 = ctypes.WinDLL("user32.dll")
    return (
        int(user32.GetSystemMetrics(76)), int(user32.GetSystemMetrics(77)),
        int(user32.GetSystemMetrics(78)), int(user32.GetSystemMetrics(79)),
        int(user32.GetSystemMetrics(80)),
    )


async def _run_non_primary_monitor_scenario() -> dict:
    """Positions the owned fixture's own window on the non-primary
    (negative-X) monitor and attempts one grounded native left click,
    independently verified via the fixture's own status label (9.11). Never
    a general production window-move capability - this flag exists only on
    the disposable evaluation fixture."""
    scenario: dict = {"attempted": True}
    vleft, vtop, vwidth, vheight, monitor_count = _virtual_desktop_metrics()
    scenario["virtual_desktop_geometry"] = {
        "x_origin": vleft, "y_origin": vtop, "width": vwidth, "height": vheight, "monitor_count": monitor_count,
    }
    if vleft >= 0 or monitor_count < 2:
        scenario["attempted"] = False
        scenario["skip_reason"] = "MULTI_MONITOR_PHYSICAL_PENDING"
        return scenario
    if not FIXTURE_HOST_SCRIPT.exists():
        scenario["attempted"] = False
        scenario["skip_reason"] = "fixture_host_script_missing"
        return scenario

    nonce = str(uuid.uuid4())
    title = f"JARVIS-CUV2-FIXTURE-{nonce}"
    target_x = vleft + 100
    runtime, identity, device, context = await _new_harness()
    proc: subprocess.Popen | None = None
    try:
        proc = subprocess.Popen(
            [sys.executable, str(FIXTURE_HOST_SCRIPT), "--nonce", nonce, "--x", str(target_x), "--y", "100"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
        )
        window_ref, error = await _find_exact_fixture_window(runtime, context, title)
        if window_ref is None:
            scenario["error"] = error
            return scenario
        invoke_ref = await _find_one(runtime, context, window_ref, "ButtonControl", "Invoke Target")
        if invoke_ref is None:
            scenario["error"] = "invoke_target_not_found"
            return scenario
        found = await runtime.tool_service.execute(
            "computer.semantic.read", {"action": "get_element", "element_ref": invoke_ref}, context
        )
        bounds = found.output.get("element", {}).get("bounds") if found.status.value == "completed" else None
        scenario["target_bounds_on_non_primary_monitor"] = bool(bounds and bounds.get("x", 0) < 0)
        status, verified, output = await _approve_and_run(
            runtime, identity, context, "computer.pointer.act", {"action": "left_click_element", "element_ref": invoke_ref}
        )
        status_after = await _read_status(runtime, context, window_ref)
        scenario["native_left_click"] = {
            "status": status,
            "pointer_target_verified": output.get("pointer_target_verified"),
            "independent_status_matches_expected": status_after == "invoked",
        }
        if scenario["target_bounds_on_non_primary_monitor"] and scenario["native_left_click"]["independent_status_matches_expected"]:
            scenario["result"] = "NON_PRIMARY_MONITOR_PHYSICAL_PASS"
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
    return {
        "owned_fixture": await _run_owned_fixture_scenarios(),
        "text_drag_fixture": await _run_text_drag_fixture_scenarios(),
        "recovery_fixture": await _run_recovery_fixture_scenarios(),
        "non_primary_monitor": await _run_non_primary_monitor_scenario(),
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

    def attempted(run: dict) -> bool:
        return bool(run["owned_fixture"].get("attempted"))

    def text_attempted(run: dict) -> bool:
        return bool(run["text_drag_fixture"].get("attempted"))

    def recovery_attempted(run: dict) -> bool:
        return bool(run["recovery_fixture"].get("attempted"))

    return {
        "runs": len(runs),
        "semantic_invoke": rate(lambda r: r["owned_fixture"].get("invoke", {}).get("independent_status_matches_expected") if attempted(r) else None),
        "semantic_toggle": rate(lambda r: r["owned_fixture"].get("toggle", {}).get("independent_status_matches_expected") if attempted(r) else None),
        "semantic_select": rate(lambda r: r["owned_fixture"].get("select", {}).get("independent_status_matches_expected") if attempted(r) else None),
        "native_left_click": rate(lambda r: r["owned_fixture"].get("native_left_click", {}).get("independent_status_matches_expected") if attempted(r) else None),
        "native_right_click_delivered": rate(lambda r: r["owned_fixture"].get("native_right_click", {}).get("input_batch_accepted") if attempted(r) else None),
        "native_double_click": rate(lambda r: r["owned_fixture"].get("native_double_click", {}).get("independent_status_matches_expected") if attempted(r) else None),
        "native_scroll_delivered": rate(lambda r: r["owned_fixture"].get("native_scroll", {}).get("input_batch_accepted") if attempted(r) else None),
        "native_key_tab": rate(lambda r: r["owned_fixture"].get("native_key_tab", {}).get("independent_focus_moved") if attempted(r) else None),
        "native_chord_completed": rate(lambda r: r["owned_fixture"].get("native_chord", {}).get("status") == "completed" if attempted(r) else None),
        "fixture_child_confirmed_exited": rate(lambda r: r["owned_fixture"].get("fixture_child_confirmed_exited") if attempted(r) else None),
        "native_drag": rate(lambda r: r["text_drag_fixture"].get("drag", {}).get("independent_status_matches_expected") if text_attempted(r) else None),
        "literal_typing_english": rate(lambda r: r["text_drag_fixture"].get("literal_typing_english", {}).get("independent_text_readback_matches_expected") if text_attempted(r) else None),
        "literal_typing_arabic": rate(lambda r: r["text_drag_fixture"].get("literal_typing_arabic", {}).get("independent_text_readback_matches_expected") if text_attempted(r) else None),
        "native_key_home_end": rate(lambda r: (r["text_drag_fixture"].get("native_key_home_end", {}).get("home_marker_prepended") and r["text_drag_fixture"].get("native_key_home_end", {}).get("end_marker_appended")) if text_attempted(r) else None),
        "native_key_backspace": rate(lambda r: r["text_drag_fixture"].get("native_key_backspace", {}).get("one_character_shorter") if text_attempted(r) else None),
        "native_key_tab_text_fixture": rate(lambda r: r["text_drag_fixture"].get("native_key_tab", {}).get("independent_focus_moved") if text_attempted(r) else None),
        "native_chord_ctrl_c_clipboard_proven": rate(lambda r: r["text_drag_fixture"].get("native_chord_ctrl_c", {}).get("clipboard_now_holds_fixture_text") if text_attempted(r) else None),
        "native_chord_ctrl_z_changed_state": rate(lambda r: r["text_drag_fixture"].get("native_chord_ctrl_z", {}).get("independent_text_changed_from_pre_undo_state") if text_attempted(r) else None),
        "text_fixture_child_confirmed_exited": rate(lambda r: r["text_drag_fixture"].get("fixture_child_confirmed_exited") if text_attempted(r) else None),
        "non_primary_monitor": {
            "attempted": any(r["non_primary_monitor"].get("attempted") for r in runs),
            "pass_count": sum(1 for r in runs if r["non_primary_monitor"].get("result") == "NON_PRIMARY_MONITOR_PHYSICAL_PASS"),
            "geometry": runs[0]["non_primary_monitor"].get("virtual_desktop_geometry") if runs else None,
        },
        "recovery_relocation_click_succeeds": rate(lambda r: r["recovery_fixture"].get("relocation_before_input", {}).get("click_landed_on_same_generation") if recovery_attempted(r) else None),
        "recovery_relocation_fresh_bounds_used": rate(lambda r: r["recovery_fixture"].get("relocation_before_input", {}).get("bounds_changed") if recovery_attempted(r) else None),
        "recovery_approval_identity_change_refused": rate(lambda r: r["recovery_fixture"].get("approval_identity_change", {}).get("refused_before_any_input") if recovery_attempted(r) else None),
        "recovery_approval_identity_change_zero_input_delivered": rate(lambda r: r["recovery_fixture"].get("approval_identity_change", {}).get("zero_input_delivered") if recovery_attempted(r) else None),
        "recovery_fixture_child_confirmed_exited": rate(lambda r: r["recovery_fixture"].get("fixture_child_confirmed_exited") if recovery_attempted(r) else None),
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
