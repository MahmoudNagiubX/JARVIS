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

---

## 5. Continuation checkpoint - Milestone 1 live OCR language-quality evaluation

This append-only continuation supersedes the pending status in Section 3. The repository was revalidated from the current feature HEAD after the M0 checkpoint; no historical report text was rewritten.

### 5.1 Evaluation boundary and runtime

M1 remained evaluation-only. There was no production change under `src/jarvis/computer/visual_ocr.py`, no new language router, and no DEC-048 decision change. The runner evaluated only the two explicit candidates below through the real `computer.visual.read` service path:

| Candidate | Reader | Explicit model files | Disk footprint |
|---|---|---|---:|
| `combined_ar_en` | `EasyOCR Reader(["ar", "en"])` | `craft_mlt_25k.pth` (83,152,330 bytes), `arabic.pth` (215,400,714 bytes) | 298,553,044 bytes |
| `english_only` | `EasyOCR Reader(["en"])` | `craft_mlt_25k.pth` (83,152,330 bytes), `english_g2.pth` (15,143,997 bytes) | 98,296,327 bytes |

The physical environment used EasyOCR 1.7.2, CPU-only `torch==2.14.0` (`2.14.0+cpu`), and CPU-only `torchvision==0.29.0` (`0.29.0+cpu`, `torch.version.cuda is None`) in the disposable evaluation venv. The model directory and all weights were outside Git, with downloads disabled and no implicit cache path.

Recorded MD5 checksums were `craft_mlt_25k.pth=2f8227d2def4037cdb3b34389dcf9ec1`, `arabic.pth=993074555550e4e06a6077d55ff0449a`, and `english_g2.pth=5864788e1821be9e454ec108d61b887d`.

The runner now records the explicit weight sizes and Windows `GetProcessMemoryInfo` working-set snapshots. The RAM figure below is the per-run working-set delta from immediately before the first OCR call to after cold/warm OCR; it is process-level evidence, not a claim that the model's virtual size equals physical RAM.

### 5.2 Three clean physical runs per candidate

| Candidate | Arabic exact gate | English recall gate | Mixed recall + Arabic substring | Warm <= 3 s | Network attempts | Working-set delta after cold OCR (bytes) |
|---|---:|---:|---:|---:|---:|---|
| `combined_ar_en` | 3/3 | 0/3 | 3/3, recall 0.933 | 2/3 | 0 | 440,528,896; 268,320,768; 347,328,512 |
| `english_only` | 0/3 | 3/3 | 0/3, recall 0.400 and Arabic substring not preserved | 3/3 | 0 | 174,923,776; 111,546,368; 140,673,024 |

All six runs completed the owned OCR window and confirmed exact child exit. Memory snapshots were available on all six runs. Warm timings were:

- `combined_ar_en`: 2,194.9 ms, 2,264.1 ms, 3,119.3 ms; cold reader initialization 2,309.6 ms, 2,267.3 ms, 2,252.7 ms.
- `english_only`: 713.0 ms, 727.1 ms, 739.2 ms; cold reader initialization 1,420.1 ms, 1,442.8 ms, 1,464.7 ms.

Candidate A preserved both pure-Arabic labels exactly in all three runs and preserved the Arabic substring in mixed text, but produced `JARMIS OCR fixture ready` (normalized recall 0.952) and `J4RVIS ... FISTURE` (normalized recall 0.812), so it failed the required 0.90 English gate and exact uppercase fixture quality. Candidate B recognized both English fixture strings exactly in all three runs, but recognized neither Arabic label and did not preserve the Arabic substring in mixed text. Neither candidate satisfied all integration gates. Candidate C was not run: the two bounded provisioned readers already demonstrated mutually exclusive gate failures, so there was no evidence-supported conditional second pass to integrate or a reason to add an unbounded reader path.

### 5.3 M1 decision

`OCR_LIVE_LANGUAGE_ROUTING_EVALUATION_NO_CHANGE`: retain the accepted production `EasyOCR Reader(["ar", "en"])` path. No production routing, model download behavior, authority, or visual actuation was added. R18B06-002 is evaluated for this batch, but the underlying live bilingual-quality limitation remains reflected by `GAP-0103: PARTIAL`.

**M1 implementation/evidence commits:** `489e015` (bounded candidate evaluation) and `03d493f` (explicit disk/RAM footprint evidence), both pushed to `origin/feature/phase-18-computer-use-v2`.

## 6. Continuation checkpoint - Milestone 2 owned multi-window/dialog evaluation

### 6.1 Fifth owned fixture and boundary

Added `scripts/phase18/uia_multi_window_fixture_host.py` as the fifth allowlisted Phase 18 fixture. It creates one nonce-scoped primary window and one owned top-level dialog, with deterministic dialog recreation and close/return state. The fixture is standalone Win32/ctypes code, has no owner application or owner data dependency, and has no network, clipboard, file-dialog, shell, or broad process-management path.

The physical runner launches and cleans up only the exact child through `owned_fixture_process.py`. Exact-title matching is followed by the existing perception authority's live `window_belongs_to_process` predicate; process identity is not exposed as model-facing window data. Failure to prove ownership fails closed. The runner emits only bounded scenario flags and reason codes, never a general window inventory or raw coordinates.

### 6.2 Deterministic evaluation

The `computer_use_v2` evaluation suite grew from 46 to 48 cases:

- `cuv2-47`: owned child-window discovery and approved dialog action;
- `cuv2-48`: stale dialog target refusal after deterministic recreation, with no input invocation.

Both cases pass through the canonical tool, approval, identity, and execution services. The Batch 07 multi-window regression set passed **4 tests**; the full owned-fixture/evaluation/native-input focused set passed **162 tests**.

### 6.3 Three clean physical iterations

The final M2 physical run passed every new scenario in all three iterations:

| Scenario | Result |
|---|---:|
| Owned dialog discovery and primary status | 3/3 |
| Dialog action and independent dialog status | 3/3 |
| Stale dialog target refused after recreation | 3/3 |
| Approval-window transition refused for stale target | 3/3 |
| Focus-window transition with fresh targets | 3/3 |
| Close dialog and return to primary window | 3/3 |
| Exact fixture child confirmed exited | 3/3 |

The final run also naturally exercised the existing non-primary-monitor geometry (`x_origin=-1920`, two monitors) without changing the owner environment. The broader legacy runner had transient foreground-activation misses in an existing text/drag fixture during this final iteration (some legacy measures were 2/3); this is recorded as environmental variance outside the new M2 gate. The new multi-window/dialog scenarios remained 3/3 throughout, and no owner application was launched or touched.

An earlier fail-closed M2 checkpoint reported `fixture_process_mismatch` because the canonical list projection did not expose a PID for the runner's ownership check. The first failing boundary was identified, and the fix reused the existing provider's validated live PID predicate without adding a second identity authority. The final physical run above is after that fix.

**M2 commit:** `60fbfb4` (`test: expand owned multi-window computer-use acceptance`), pushed to `origin/feature/phase-18-computer-use-v2`.

## 7. Final verification and verdict

### 7.1 Repository checkpoint

- Starting HEAD: `2e746fd6e74da1a53d6d479ab8be752f4c876152`.
- Final code HEAD before this report append: `03d493ffa76f20a6d9b79a409292a64f5e5c9049`.
- Branch: `feature/phase-18-computer-use-v2`.
- `origin/main`: `54b67ba396ec45180f1b60ea472ef94c9ac181a9`.
- Feature HEAD `03d493f` was pushed; no reset, rebase, merge, force push, or owner-app probe was used.

### 7.2 Verification

- Focused Batch 07 safety/evaluation/native-input set: **162 passed**.
- Phase 18/OCR selection: **325 passed, 3 skipped, 515 deselected**. The three skips are the optional `easyocr`, `torch`, and `torchvision` reproducibility checks in the repository's normal `.venv`; the real optional runtime was verified in the disposable physical evaluation venv above.
- Full repository suite: **840 passed, 3 skipped, 36 subtests passed**.
- `python -m compileall src tests scripts -q`: clean.
- `git diff --check`: clean.
- `computer_use_v2` case count: **48**.

### 7.3 Final gap and restriction truth

- `GAP-0101`: `RESOLVED`.
- `GAP-0102`: `PARTIAL`.
- `GAP-0103`: `PARTIAL` (read-only OCR; M1 retained the current bilingual baseline after no candidate passed all live gates).
- `GAP-0104`: `PARTIAL` (bounded pre-input recovery; no autonomous multi-app replanning loop).
- `GAP-0105`: `PARTIAL` (evaluation foundation expanded to 48 cases and five owned fixtures; no broad real-app matrix).
- `GAP-0106`: `PARTIAL`.
- `GAP-0503`: `RESOLVED_AFTER_REVIEW_HARDENING` for the current path-read scope.

The permanent restrictions remain unchanged: local-first/offline operation, canonical permission/approval/audit authority, read-only OCR, no visual actuation, no autonomous multi-app replanning, no owner-app physical probing, no owner clipboard/profile/file access, bounded fixture launches only, and exact-child cleanup only.

**Final verdict: `PHASE18_COMPUTER_USE_BATCH07_PASS`** - M0 safety hardening is pushed, M1 completed its required live candidate evaluation with a justified no-change decision, and M2's owned multi-window/dialog gate is green at 3/3. This verdict does not promote the remaining `PARTIAL` product gaps to complete and does not claim broad real-application or physical human acceptance.
