# Phase 18 Workstream A - Batch 09 Audit

**Status:** T0 PASS; T1 `IMPLEMENTED`; T2 `RW-CALC-001` physical gate PASS
(3/3 clean runs); Brave binary provenance PASS but host open/focus remains
`PARTIAL` after fail-closed ambiguity; browser navigation/authentication is a
`CROSS_WORKSTREAM_BLOCKER`. Batch 09 remains `PARTIAL`. T3-T6 were not started.
Calculator and Brave host windows were touched only under the explicit local
owner-session opt-in; no owner account, browser profile, inbox, chat, document,
or media session was used.

**Repository:** `MahmoudNagiubX/JARVIS`
**Branch:** `feature/phase-18-computer-use-v2`
**Required continuation HEAD:** `dbd3f93b658968b56e11a54a76c0cf620515a159`
**T0 implementation checkpoint:** `ca1cbe32c3246c8495cb65f4deba9dc72f2e4921`
**T1 implementation checkpoint:** `89724436d7eec228374b39de8b7a33092fb5d872`
**Prior T2 Calculator implementation checkpoint:** `5a42e5f`
**Continuation evidence:** recorded below; final code/docs checkpoint is the
feature-branch commit produced after verification.
**Origin main:** `54b67ba396ec45180f1b60ea472ef94a9`

## 1. T0 profile and fix

The pre-fix owned-fixture baseline at the required starting HEAD could not
complete the visual happy path within the 30-second visual-reference lifetime.
The bounded diagnostic trace measured the following representative timings
after visual-reference issuance:

| Stage | Measured latency |
|---|---:|
| Initial OCR observation | 6660.6 ms |
| Approval-preview resolution | 3889.1 ms |
| Decide-time resolution | 3951.9 ms |
| Controller pre-focus resolution | 3842.4 ms |
| Foreground call | 0.3 ms |
| Post-focus fresh OCR | 3729.3 ms |
| Reference issuance to first input | approximately 15.4 s |

The old sequence performed four post-issuance OCR resolutions before native
input. T0 now carries the already-trusted target from the canonical approval
service into local controller execution. The target is still checked against
the exact visual reference and expiry; foreground verification is unchanged;
decide-time target binding remains strict; and post-focus OCR remains a fresh
revalidation. No raw frame or geometry is cached or exposed.

The production visual-reference TTL remains 30 seconds. No TTL widening,
foreground bypass, coordinate fallback, or post-input retry was added. The
source-window reference remains governed by the existing bounded provider
lifetime; no independent source-window TTL was changed by T0.

## 2. T0 physical receipt

Command used the existing isolated EasyOCR environment and the existing
JARVIS-owned `scripts/phase18/uia_ocr_fixture_host.py` only. The temporary
receipt was written outside the repository.

Receipt: `<local-temp>\jarvis_batch09_t0_postfix.json` (outside the repository)

| Gate | Result |
|---|---:|
| A happy visual left click | 3/3 |
| B stale target refusal and zero input | 3/3 |
| C duplicate-label ambiguity and zero input | 3/3 |
| D approval drift refusal and no migration | 3/3 |
| E post-input uncertainty and no automatic second click | 3/3 |
| Network attempts | 0 |
| Exact child cleanup | 3/3 |

The physical receipt verdict was `PASS`. The result is owned-fixture evidence
for the visual actuation foundation; it is not evidence for any owner app.

## 3. Bug audit entry

**ID:** `R18B09-001`
**Scenario:** T0 / A happy visual left click
**Observed:** The pre-fix path could spend the short visual-reference lifetime
on redundant OCR resolutions before input and fail the happy path.
**Expected:** One approval-bound target should reach foreground-safe input while
retaining a fresh post-focus visual revalidation.
**Root cause:** The same trusted visual target was resolved again in the
controller before focus after approval creation and decide-time validation.
**Security impact:** The fix carries only an internal provider target through
the existing canonical service boundary. It does not expose bounds, OCR text,
HWNDs, or frames; it does not weaken approval binding, expiry, foreground
verification, or post-focus revalidation.
**Wrong-action count:** 0
**Was side effect delivered?:** No in the failing baseline; the post-fix owned
fixture delivered the intended bounded click in 3/3 runs.
**Deterministic reproduction:** Run the visual approval path with a 30-second
visual reference and instrument each resolver; the pre-fix sequence contains
the duplicate controller resolution.
**Regression test:** `SchemaAndCoreStartupTests.test_visual_act_reuses_decision_target_but_keeps_post_focus_ocr` and the existing visual stale/drift/uncertainty tests.
**Fix:** Internal-only `VisualTarget` handoff from the approval preview through
`ComputerActionService` to the local controller; expiry/ref equality checks
remain fail-closed.
**Commit:** `ca1cbe3`
**Post-fix tests:** 170 focused evaluation/visual/native tests passed; T0
physical receipt A-E passed 3/3.
**Real-world rerun:** Not applicable to T0; owner applications were not used.
**Remaining limitation:** Full real-world app acceptance is not yet proven.

## 4. T1 owner-session boundary

Added `scripts/phase18/real_world_computer_use_acceptance.py` as an evaluation
tool, not a new authority. It has:

- exact `JARVIS_E2E_ENABLE_OWNER_SESSION=1` opt-in;
- the nine finite Batch 09 scenario IDs and no arbitrary dispatch;
- bounded owner/runtime identity configuration with no identity creation;
- first-party HTTPS domain validation;
- explicit Discord destination validation and rejection of last-contact/fuzzy
  selection rules;
- login preflight states including `OWNER_LOGIN_REQUIRED`, with zero tool
  execution before `READY`;
- lazy production imports and delegation through the existing runtime tool
  service only;
- generated `JARVIS_E2E_<UTC_TIMESTAMP>_<SHORT_UUID>` nonce support;
- receipts containing bounded status/counters and destination hashes only;
- no normal-startup, pytest, CI, or scheduler trigger.

For this continuation, the exact opt-in and an existing active/enrolled local
owner identity/device were supplied only through the process environment. No
identity was created and no owner-specific value was written to the repository.
The production session resolves the configured owner to the canonical identity
row before loading the identity object, then validates the existing device
owner binding. The current runtime still exposes the bounded local HTTP browser
controller rather than a real authenticated Brave/session adapter.

T1/T2 boundary tests: `tests/test_phase_eighteen_real_world_boundary.py` - 22
passed after the continuation fixes.

## 5. T2 physical gates

### 5.1 RW-CALC-001 — Calculator

The default handler for `RW-CALC-001` exercises the existing typed
`ComputerActionService` for allowlisted Calculator launch/focus, then uses the
existing semantic read/action tool path for the UI. It requires:

- exactly one opaque window with title `Calculator` and an allowlisted
  Calculator process name;
- exact semantic button grounding for `Clear`, `One`, `Seven`, `Multiply by`,
  `Two`, `Three`, and `Equals`, with ambiguity refused;
- one approval decision for each consequential semantic invoke; and
- a fresh semantic text readback that independently finds and reads `391`.

The handler never trusts the action's self-reported verification and returns
`FAILED` on ambiguous windows/controls, unavailable UIA, focus drift, approval
failure, or result mismatch. The final explicit owner-session run used
`--runs 3` and was recorded outside the repository as
`<local-temp>\jarvis_batch09_calc_20260915_r004.json`:

| Check | Result |
|---|---:|
| Clean physical runs | 3/3 `PASS` |
| Independent readback | 3/3 `Display is 391` |
| Consequential approvals | 21 total (7/run) |
| Wrong targets | 0 |
| Duplicate/unapproved sends | 0 / 0 |
| External writes/sends | 0 / 0 |

The owner opt-in, existing identity, and existing enrolled device were
process-local configuration only. The immediate bug-fix loop is recorded in
§5.4 below. Both fixes have deterministic regression coverage, and the final
physical receipt is the required clean 3/3 result.

### 5.2 RW-BRAVE-001 — Brave host-only preflight

The safe installation inspection checked only these standard locations, using
explicit path checks (no installer, recursive scan, or machine-wide search):

- `%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe`
- `%ProgramFiles(x86)%\BraveSoftware\Brave-Browser\Application\brave.exe`
- `%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe`

An existing binary was found at the local-user `%LOCALAPPDATA%` location. The
full username-bearing path is intentionally redacted in this committed audit;
the exact path was supplied only through process-local configuration. Observed
provenance:

| Property | Observed value |
|---|---|
| Version | `153.1.95.101` |
| Publisher/company | `Brave Software, Inc.` |
| Authenticode | `Valid` (`Signature verified.`) |
| Signer | `CN="Brave Software, Inc."` |
| Issuer | `DigiCert Trusted G4 Code Signing RSA4096 SHA384 2021 CA1` |
| SHA-256 | `BDA9ED87B3A04D9C474768B66660681BF1D9E9D6CE03D53D98909FAB9B5CC624` |

The host-only runner was invoked with the exact local path and `--runs 3`.
Canonical allowlisted launch used the fixed product-owned `--new-window`
argument; callers cannot supply arbitrary flags. The final host attempt was:

| Check | Result |
|---|---:|
| Host attempts | 3 |
| Unique Brave window/focus proofs | 0/3 |
| Result | 3/3 `FAILED brave_window_ambiguous` |
| Host baseline | 0/3 |
| Focus/navigation actions delivered | 0 / 0 |
| External writes/sends | 0 / 0 |

Existing Brave windows remained an ambiguous set after launch (the last
transient observation contained seven exact Brave windows, all inactive). The
runner therefore refused to choose by title, geometry, list order, or raw
window handle. No focus was attempted after the ambiguous grounding result,
and no browser tab, page content, domain, account, cookie, or credential was
inspected.

### 5.3 Cross-workstream boundary

The current production browser component is `LocalBrowserController`, a
bounded HTTP/parser path; it is not a live authenticated Brave/session adapter
or Browser V2/Playwright implementation. Actual Brave navigation or
authenticated web control is therefore classified as
`CROSS_WORKSTREAM_BLOCKER` under `GAP-0201`. No Playwright dependency, second
browser authority, navigation, login automation, or fake browser acceptance
was added.

### 5.4 T2 physical bug audit

**ID:** `R18B09-002`
**Scenario:** `RW-CALC-001` window grounding/focus
**Observed:** The first owner-session attempts returned
`calculator_window_ambiguous`; after the opaque-reference selection was
corrected, the next attempts could still lose foreground state during launch.
**Root cause:** the Windows desktop provider issues fresh opaque references on
each semantic snapshot, while Calculator's UWP host can expose existing exact
siblings before the new launch settles. Comparing references across snapshots
was invalid and selecting a stale active sibling made focus verification race.
**Fix:** select from one post-launch snapshot after a bounded two-second settle,
then independently require one exact active Calculator candidate after the
canonical focus action. Ambiguity remains a fail-closed stop before input.
**Regression:** `test_calculator_handler_targets_new_window_around_stale_exact_windows`,
`test_calculator_handler_settles_launch_before_grounding_exact_window`, and the
ambiguity refusal test in `tests/test_phase_eighteen_real_world_boundary.py`.
**Physical impact:** no wrong target, duplicate send, or unapproved send was
recorded in the failing attempts; the final receipt passed 3/3.

**ID:** `R18B09-003`
**Scenario:** `RW-CALC-001` independent result verification
**Observed:** the first settled Calculator runs reached the UI but returned
`calculator_result_mismatch`.
**Root cause:** the live UIA surface exposed the result through the stable
`CalculatorResults` AutomationId with text `Display is 391`, not a bare `391`
TextControl value.
**Fix:** find exactly one `CalculatorResults` element and accept only the
bounded normalized forms `391` or `Display is 391`; action self-report is not
used.
**Regression:** the exact AutomationId/readback behavior is covered by the
Calculator handler tests. The final physical receipt independently read
`Display is 391` in 3/3 runs.

**ID:** `R18B09-004`
**Scenario:** `RW-BRAVE-001` host open/focus
**Observed:** the initial three-run attempt and the follow-up after adding the
fixed product-owned `--new-window` launch argument both found multiple exact
Brave windows with no unique active candidate.
**Root cause:** Brave handed the new-window request to an existing singleton
process, leaving the semantic top-level window set ambiguous; the current
canonical semantic listing intentionally does not expose raw handles or a
model-facing window discriminator that would make list order/geometry safe.
**Fix/stop condition:** allowlist `brave.exe`, resolve the exact configured
path through a process-local `PATH` prefix, use only the fixed `--new-window`
argument, settle briefly, and refuse to focus when exact candidates remain
ambiguous. Closing or choosing an existing owner window would be unsafe and
was not attempted.
**Regression:** `test_brave_host_refuses_multiple_inactive_windows_before_focus`,
`test_brave_host_baseline_stops_at_browser_v2_boundary`, and
`BraveLauncherTests.test_brave_launcher_uses_allowlisted_name_and_shell_false`.
The physical result remains 3/3 fail-closed, with no focus/navigation action,
external write, send, account, or credential interaction.

## 6. Verification checkpoint

- `python -m pytest tests/test_phase_eighteen_visual_ocr.py -q` - 65 passed.
- `python -m pytest tests/test_phase_eighteen_evaluation_suite.py tests/test_phase_eighteen_visual_ocr.py tests/test_phase_eighteen_native_input.py -q` - 170 passed.
- `python -m pytest tests/test_phase_eighteen_real_world_boundary.py -q` - 22 passed after the continuation fixes.
- `python -m pytest tests -q` - 902 passed, 4 skipped, 41 subtests passed; the
  skips are the three known optional EasyOCR/Torch/Torchvision interpreter
  dependencies plus the environment-sensitive active-window test when no
  active Windows window is available.
- `python -m compileall src tests scripts -q` - pass.
- `git diff --check` - pass at each checkpoint.
- The opt-in-without-identity Calculator probe returned
  `NOT_CONFIGURED/owner_runtime_identity_not_configured`, with zero completed
  runs and zero external writes/sends.
- The T0/T1 checkpoints were already committed and pushed. This continuation
  is limited to T2 physical evidence, its immediate bug-fix loop, the Brave
  host boundary, and truthful documentation; final commit/push verification is
  recorded at handoff.

## 7. Remaining Batch 09 gates

`RW-CALC-001` is closed for this bounded Calculator slice at 3/3. The Brave
host/focus gate remains `PARTIAL` because safe unique-window grounding was not
proven on the current desktop. The Brave web/navigation portion is a
`CROSS_WORKSTREAM_BLOCKER` until Browser V2 provides the approved live adapter.
Batch 09 therefore remains `PARTIAL`; T3-T6 were not started. No login
automation, credential inspection, arbitrary recipient selection, owner-history
inspection, raw screenshot persistence, or Playwright/Browser V2 scope
expansion was performed.
