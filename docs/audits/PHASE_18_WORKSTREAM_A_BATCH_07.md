# PHASE 18 — WORKSTREAM A — BATCH 07
## Executor Contract → Physical-Test Safety → Live OCR Quality → Owned Multi-Window/Dialog Evaluation

**Task:** `C:\Users\mahmo\Downloads\CODEX_MASTER_PHASE_18_WORKSTREAM_A_BATCH_07_LUNA_MAX.md`
**Executor:** Codex
**Owner-selected model/session:** GPT-5.6 Luna / Max, per the supplied handoff. The available client surface did not expose an independent model/effort status readout, so this is not claimed as an observed runtime value.
**Branch:** `feature/phase-18-computer-use-v2`
**Starting HEAD:** `2e746fd6e74da1a53d6d479ab8be752f4c876152`
**Expected `origin/main`:** `54b67ba396ec45180f1b60ea472ef94c9ac181a9`
**Status:** Milestone 0 implementation complete locally; push/restart checkpoint and Milestones 1–2 remain pending.

## 1. Preflight

- Working tree was clean before edits.
- Branch matched `feature/phase-18-computer-use-v2`.
- Local and remote feature HEAD matched `2e746fd6e74da1a53d6d479ab8be752f4c876152`.
- `origin/main` matched `54b67ba396ec45180f1b60ea472ef94c9ac181a9`.
- Recent history matched the expected Batch 06 chain; no reset, checkout, rebase, force push, or merge was used.

## 2. Milestone 0 — Codex / physical-test safety hardening

### 2.1 Executor change

Batch 07 changes the implementation executor from the historical Cloud Code / Claude Code workflow to Codex. The architecture is unchanged: one canonical permission/approval/audit path, one `ComputerActionService`, and fixture processes remain development-only execution/perception seams. No product architecture decision was added for executor preference.

### 2.2 Root contract

`AGENTS.md` now has a permanent Physical acceptance safety section requiring:

- JARVIS-owned `scripts/phase18/` fixtures only;
- fresh nonce and exact-title discovery;
- exact child PID/object ownership and terminate/wait/kill cleanup;
- no similar-title/first-match fallback or broad process kill;
- no owner clipboard, files, documents, profiles, sessions, or general applications;
- physical evidence remains pending when no safe owned fixture exists.

The stale Active work sentence now records that Batch 07 Milestone 0 safety hardening is complete and the bounded OCR and multi-window/dialog milestones remain pending.

### 2.3 Central launch boundary

Added `scripts/phase18/owned_fixture_process.py`. It:

- resolves paths component-wise beneath the Phase 18 fixture directory;
- accepts only the explicit allowlist of `uia_fixture_host.py`, `uia_text_fixture_host.py`, `uia_ocr_fixture_host.py`, and `uia_recovery_fixture_host.py`;
- accepts a UUID nonce and the narrowly supported fixture position pair;
- fixes stdout/stderr to `DEVNULL` and permits a private stdin pipe only for the recovery fixture;
- invokes only the current Python interpreter plus the validated fixture script;
- returns the exact child `Popen` object;
- terminates/waits/kills only that exact child object, with no image-name lookup.

`computer_use_acceptance.py` and `ocr_visual_acceptance.py` now route every physical launch and cleanup operation through this helper. Fixture host scripts themselves were not broadened or connected to production.

### 2.4 Static safety evidence

Added regression coverage in `tests/test_phase_eighteen_owned_fixture.py` for helper path/allowlist rejection, current-interpreter launch construction, exact-child cleanup fallback, runner routing, exact nonce-title matching, and absence of broad process kills. No forbidden application was launched by these tests or during this milestone.

### 2.5 Verification at report creation

- `python -m pytest tests/test_phase_eighteen_owned_fixture.py -q` → **48 passed**.
- `python -m pytest tests/test_phase_eighteen_evaluation_suite.py -q` → **7 passed**.
- `git diff --check` → clean.
- Static search found the only executable `subprocess.Popen` call in the central helper; active physical runners contain no direct launch call, no broad `taskkill`, and no forbidden-app command.
- Physical acceptance was not run as part of this safety-only checkpoint; no owner/general application was launched or touched.

**M0 commit:** `8cdb77515cfbe296281248a4c36461cbd0e17779` (`fix: harden owned physical acceptance boundaries`).
**M0 push:** confirmed on `origin/feature/phase-18-computer-use-v2` at `2e0026e750a92c1a057f2bb959a53659f4458f05`.

## 3. Milestones still pending

Milestone 1 must evaluate the current owned OCR fixture first, with three clean runs per bounded candidate and no production integration unless all handoff gates pass. If no strategy passes, preserve EasyOCR and document the no-change result.
Milestone 2 must add an owned multi-window/dialog fixture and deterministic/physical scenarios without substituting an owner application. A fresh Codex session from the repository root is required before either milestone begins so the new root `AGENTS.md` contract is loaded.

## 4. Gap and restriction truth at this checkpoint

No product gap state changed in Milestone 0:

- GAP-0101: `RESOLVED` for the core semantic capability;
- GAP-0102: `PARTIAL`;
- GAP-0103: `PARTIAL`, read-only OCR only;
- GAP-0104: `PARTIAL`, bounded pre-input recovery only;
- GAP-0105: `PARTIAL`, owned-fixture evaluation foundation only;
- GAP-0106: `PARTIAL`;
- GAP-0503: `RESOLVED_AFTER_REVIEW_HARDENING` for current path-read confinement only.

The following restrictions remain in force: no visual actuation, no autonomous multi-app replanning loop, no broad real-app matrix, no owner-app physical probing, no owner clipboard/profile/file access, no arbitrary executable launch boundary, and no broad process termination. Final Batch 07 verdict and complete evidence remain pending until the later milestones are either completed or truthfully documented as blocked/partial.
