# Phase 18 Workstream A - Batch 09 Audit

**Status:** T0 PASS; T1 implemented; T2 is pending the required fresh Codex
session after the narrow `AGENTS.md` clarification. No owner application,
account, browser profile, inbox, chat, document, or media session was touched.

**Repository:** `MahmoudNagiubX/JARVIS`
**Branch:** `feature/phase-18-computer-use-v2`
**Required starting HEAD:** `33302eccc9337c47a83f3d98a10293356575e70c`
**T0 implementation checkpoint:** `ca1cbe32c3246c8495cb65f4deba9dc72f2e4921`
**T1 implementation checkpoint:** `89724436d7eec228374b39de8b7a33092fb5d872`
**Origin feature:** matches final checkpoint
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

Receipt: `C:\Users\mahmo\AppData\Local\Temp\jarvis_batch09_t0_postfix.json`

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

The current machine has no Batch 09 owner-session opt-in or destination
configuration. The current runtime also exposes the bounded local HTTP browser
controller rather than a real authenticated Brave/session adapter. The runner
therefore reports `OWNER_SESSION_E2E_DISABLED` or `NOT_CONFIGURED` and performs
no owner-side action until explicit local configuration and a reviewed
production adapter are available.

T1 tests: `tests/test_phase_eighteen_real_world_boundary.py` - 12 passed.

## 5. Verification checkpoint

- `python -m pytest tests/test_phase_eighteen_visual_ocr.py -q` - 65 passed.
- `python -m pytest tests/test_phase_eighteen_evaluation_suite.py tests/test_phase_eighteen_visual_ocr.py tests/test_phase_eighteen_native_input.py -q` - 170 passed.
- `python -m pytest tests/test_phase_eighteen_real_world_boundary.py -q` - 12 passed.
- `python -m py_compile scripts/phase18/real_world_computer_use_acceptance.py` - pass.
- `git diff --check` - pass at each checkpoint.
- The T0 fix was committed and pushed; remote feature verification matched the
  final checkpoint.

## 6. Remaining Batch 09 gates

T2-T6 remain pending. Per the task contract, T2 must begin in a fresh Codex
session after the `AGENTS.md` clarification is reloaded. Brave is not present
on PATH and no owner Notion, Spotify, Discord, WhatsApp, or browser-session
configuration is present in this environment. No login automation, credential
inspection, arbitrary recipient selection, owner-history inspection, raw
screenshot persistence, or Playwright/Browser V2 scope expansion was performed.
