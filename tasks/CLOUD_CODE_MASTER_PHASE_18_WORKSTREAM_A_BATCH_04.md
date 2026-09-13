# CLOUD CODE MASTER TASK — PHASE 18 WORKSTREAM A — BATCH 04
# FILE-SEARCH BOUNDARY HARDENING → GROUNDED DRAG + OWNED TEXT EVALUATION → LOCAL VISUAL GROUNDING / OCR V1

**Project:** JARVIS  
**Owner:** Mahmoud  
**Target coding agent:** Cloud Code / Claude Code  
**Date:** 2026-09-13  
**Repository:** `MahmoudNagiubX/JARVIS`  
**Local repo root:** `C:\Jarivs\00_final\jarvis`  
**Branch:** `feature/phase-18-computer-use-v2`  
**Expected starting HEAD:** `7188c712563a9340112da1b86fcd218d71898af1`

---

# 0. EXECUTION CONTRACT

You begin with **zero prior chat/session context**.

This is intentionally one substantial master task. Do not ask the owner to run a sequence of tiny follow-up tasks.

Internally, however, execute the batch as three bounded milestones:

1. **Milestone 0 — close the independent-review file-search boundary follow-up**
2. **Milestone 1 — add grounded element-to-element drag + a second JARVIS-owned text/input fixture and broaden physical evaluation**
3. **Milestone 2 — build Local Visual Grounding / OCR V1 as a read-only fallback behind the existing Computer Use authority**

For each milestone:

```text
inspect only relevant current code
→ implement only that milestone
→ focused tests
→ required full regression
→ inspect diff/security boundaries
→ update truthful canonical state
→ explicit staging
→ commit
→ push same feature branch
→ continue automatically only if green
```

After all milestones:

```text
final full regression
→ final security review
→ finish one Batch 04 report
→ final docs-only commit if report/state needs SHA/results backfill
→ push
→ STOP
```

Do not merge to `main`.

Do not squash.

Do not amend already-pushed commits.

Do not force-push.

Do not reset/stash/clean owner work.

---

# 1. EXPECTED START STATE

Run before any edit:

```powershell
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git status --short
git log --oneline --decorate -15
git remote -v
```

Expected:

```text
repo root: C:\Jarivs\00_final\jarvis
branch: feature/phase-18-computer-use-v2
HEAD: 7188c712563a9340112da1b86fcd218d71898af1
```

Expected Batch 03 history immediately behind HEAD:

```text
7188c712  docs: finalize phase 18 batch 03 report
5aaa69c9  feat: expand grounded input and computer-use evaluation
a21ae23d  fix: confine computer file access to approved roots
e4bfbcc0  fix: harden computer target approvals and fixtures
```

If HEAD differs because the owner intentionally added a later commit, inspect it before proceeding.

If divergence is unexplained:

`STOP_UNEXPLAINED_HEAD_DIVERGENCE`

Do not modify history to make the expected SHA appear.

---

# 2. MINIMAL REQUIRED READ SET

Do not read the historical 2MB+ Master unless an actual contradiction requires it.

Read:

1. `AGENTS.md`
2. `docs/source_of_truth/01_JARVIS_CORE_SOURCE_OF_TRUTH.md`
3. `docs/source_of_truth/02_JARVIS_CURRENT_STATE.md`
4. `docs/source_of_truth/03_JARVIS_GAP_REGISTER.md`
5. `docs/source_of_truth/04_JARVIS_EXECUTION_ROADMAP.md`
6. `docs/source_of_truth/05_JARVIS_DECISION_LOG.md`
7. `docs/audits/PHASE_18_WORKSTREAM_A_BATCH_03.md`

Then inspect only referenced code.

## Milestone 0 read set

- `src/jarvis/computer/file_access.py`
- file operations inside `src/jarvis/computer/service.py`
- `src/jarvis/config.py`
- `src/jarvis/bootstrap.py`
- `tests/test_phase_eighteen_file_access.py`

## Milestone 1 read set

- `src/jarvis/computer/native_input.py`
- `src/jarvis/computer/service.py`
- `src/jarvis/contracts/computer.py`
- `src/jarvis/tools/registry.py`
- `src/jarvis/perception/windows.py`
- `src/jarvis/computer/semantic_uia.py`
- `scripts/phase18/uia_fixture_host.py`
- `scripts/phase18/computer_use_acceptance.py`
- `src/jarvis/evaluation/computer_use_v2.py`
- Phase 18 native/owned-fixture/evaluation tests

## Milestone 2 read set

Inspect existing screenshot/perception code first:

- `src/jarvis/perception/`
- specifically the current bounded screen/window capture implementation
- `src/jarvis/contracts/`
- `src/jarvis/computer/service.py`
- `src/jarvis/tools/registry.py`
- `src/jarvis/evaluation/computer_use_v2.py`
- `src/jarvis/models/` only if a visual-model dependency is actually needed
- `pyproject.toml`
- existing optional-dependency conventions

Do not read unrelated voice/home/VENOM code.

---

# 3. LOCKED ARCHITECTURE — PRESERVE

JARVIS is one personal AI operating system, not independent mini-agents with duplicate authority.

Preserve:

```text
AgentRuntime
→ ToolExecutionService
→ PermissionEngine
→ ApprovalEngine when consequential
→ ComputerActionService
→ product-owned semantic/native/visual adapters
→ OS
→ fresh independent observation
→ truthful result
→ audit/events
→ model/user
```

Do not create:

- `ComputerActionServiceV2`
- `VisualComputerActionService`
- a second PermissionEngine
- a second ApprovalEngine
- a second audit authority
- raw model → OCR library
- raw model → `SendInput`
- raw model → GDI/screenshot API
- raw model → filesystem
- unrestricted shell or PowerShell tool
- arbitrary coordinate actuation

Visual/OCR is a **provider behind existing authority**, not a new authority.

---

# 4. GLOBAL SECURITY / PRIVACY RULES

Preserve all existing restrictions:

- local-first;
- offline-capable after required local model assets are installed/cached;
- no cloud OCR API;
- no API key;
- no owner credential;
- no screenshot/frame persistence by default;
- no screenshot/frame → Memory;
- no OCR output → durable Memory automatically;
- no secret/token/password/private-key extraction path;
- sensitive-window policy applies before capture/OCR;
- no secure-desktop/UAC bypass;
- no elevation/UIAccess request;
- no arbitrary raw coordinates from the model;
- no raw HWND in model-facing schemas;
- no raw COM object;
- no raw virtual-key code;
- no unrestricted hotkey parser;
- no file-dialog automation in this batch;
- no file write/move/copy/rename/delete in this batch;
- no clipboard paste in this batch;
- no visual actuation in this batch.

Milestone 2 is **read-only visual grounding**.

Visual click/actuation belongs to a later independently-reviewed batch.

---

# 5. INDEPENDENT REVIEW FINDING AFTER BATCH 03

Batch 03 is accepted as a strong foundation, but independent review found one real boundary mismatch.

---

## R18B03-001 — search filters external junction results after traversal rather than preventing traversal

Current implementation conceptually performs:

```python
root.rglob(pattern)
→ candidate.resolve()
→ discard candidate if resolved outside approved root
```

This prevents outside files from being returned to the model.

That is good.

But it does not satisfy the stronger policy requirement:

> search traversal itself must not descend through a symlink/junction/reparse point whose target escapes the approved root.

The current test even materializes:

```python
candidates = list(allowed_root.rglob("*"))
```

then proves that outside candidates are filtered.

So the final model-visible result is safe, but the filesystem boundary is still looser than intended because enumeration may already occur outside the approved root before filtering.

### Risk classification

Not a current model-visible data leak.

Not a rollback issue.

Still a real defense-in-depth / least-authority defect.

### Required fix

Replace unbounded `Path.rglob()` traversal with a product-owned bounded walker that decides **before descending**.

At each directory:

1. canonicalize the directory;
2. verify it remains inside the canonical approved root;
3. inspect whether it is a symlink/junction/reparse point;
4. if the entry can escape or cannot be safely classified:
   - do not descend;
   - increment bounded hidden/filtered count if appropriate;
5. only enumerate children of an approved non-escaping directory;
6. apply candidate count and result count bounds during traversal, not after creating a huge candidate list.

Never build an unbounded list first.

### Windows junction handling

The project supports Python 3.12+ and currently runs on Windows 11.

Use supported Python/Windows APIs to detect junction/reparse boundaries.

Prefer stdlib support when available.

Do not introduce a third-party filesystem library solely for this.

If an entry's link/junction/reparse classification is uncertain:

fail closed by not descending.

### Search output

Keep current safe behavior:

- outside path is never returned;
- sensitive path name is never returned;
- optional `filtered_count` remains bounded;
- no hidden path details.

---

## R18B03-002 — `.env` sensitive-family match is too exact

Current sensitive filename set catches explicit names such as:

- `.env`
- `.env.local`
- `.env.development`
- `.env.production`
- `.env.test`

But common variants include:

- `.env.staging`
- `.env.development.local`
- `.env.production.local`
- `.env.test.local`

and similar `.env.<suffix>` files.

### Required fix

Treat:

```text
.env
.env.*
```

as sensitive,

except the explicitly safe template:

`.env.example`

Do not accidentally classify unrelated names such as:

`.environment`

as `.env.*`.

Tests must cover:

- `.env`
- `.env.local`
- `.env.staging`
- `.env.development.local`
- `.env.production.local`
- `.env.example` allowed
- `.environment` not denied by the `.env` rule alone

---

# 6. MILESTONE 0 — FILE SEARCH BOUNDARY HARDENING

## 6.1 Implement pre-descent bounded walker

Keep `FileAccessPolicy` as the one policy.

Do not create a second file authority.

Preferred shape:

```text
FileAccessPolicy.iter_search_candidates(...)
```

or equivalent.

The traversal function should own:

- pre-descent root containment;
- reparse/link classification;
- sensitive subtree pruning;
- candidate scan budget;
- result limit cooperation;
- error handling.

Do not leave root traversal in `ComputerActionService`.

`ComputerActionService` should ask the policy for safe candidates/results.

---

## 6.2 Traversal requirements

Hard bounds:

```text
MAX_SEARCH_CANDIDATES_SCANNED <= existing 5000
MAX_SEARCH_MATCHES <= existing 100
```

Also introduce a maximum directory depth if current design has none.

Recommended initial bound:

`MAX_SEARCH_DEPTH = 32`

Do not allow cyclic traversal.

Keep a canonical-directory visited set if needed.

Visited set itself must be bounded.

---

## 6.3 Reparse / symlink / junction policy

Default:

> do not follow directory symlinks/junctions/reparse points during generic file search.

This is deliberately stricter than "follow if still inside root".

Reason:

- simpler;
- deterministic;
- avoids cycles;
- avoids mount/junction ambiguity;
- search does not need link traversal for JARVIS's current minimal feature.

A file symlink may be returned only if:

- final resolved file is still inside approved root;
- sensitive policy passes;
- behavior is explicitly tested.

If simpler/safer:

skip all reparse/symlink entries.

Document the choice.

Do not weaken direct `inspect_file` confinement; it still resolves and checks the real target.

---

## 6.4 Search pattern

Preserve existing bounded pattern interface.

No arbitrary regex engine.

No shell glob expansion.

No shell.

Pattern length remains bounded.

---

## 6.5 Required tests

Add red-before-green tests proving:

1. junction target outside root is **not traversed**
2. walker never yields the external secret candidate even temporarily
3. symlink/junction directory inside root is not descended
4. cycle cannot cause unbounded walk
5. scan count <= hard bound
6. result count <= hard bound
7. sensitive subtree is pruned
8. hidden sensitive child name does not appear in output
9. `.env.staging` denied
10. `.env.development.local` denied
11. `.env.production.local` denied
12. `.env.example` allowed
13. `.environment` unaffected by the `.env.*` rule
14. normal nested search still succeeds

Use temp directories only.

No owner files.

---

## 6.6 Canonical status

GAP-0503 should be treated as:

`RESOLVED_AFTER_REVIEW_HARDENING`

only if the new pre-descent traversal passes.

Do not expand GAP-0503 scope to mean file write/file dialogs are implemented.

The resolved scope remains:

> current read/open/search path confinement.

---

## 6.7 Verification

```powershell
python -m pytest tests/test_phase_eighteen_file_access.py -q
python -m pytest tests -k "file_access or phase_eighteen" -q
python -m pytest tests -q
python -m compileall src tests scripts -q
git diff --check
```

---

## 6.8 Commit

Commit message:

`fix: harden confined file search traversal`

Push:

```powershell
git push origin feature/phase-18-computer-use-v2
```

Record:

`MILESTONE_0_COMMIT`

Continue only if green.

---

# 7. MILESTONE 1 — GROUNDED DRAG + SECOND OWNED FIXTURE + EVALUATION BREADTH

## Goal

Advance GAP-0102 and GAP-0105 without reintroducing raw coordinates or owner-application testing.

This milestone adds:

1. one bounded drag primitive;
2. a second JARVIS-owned physical fixture focused on text/input;
3. broader physical acceptance through the actual canonical tool path.

No paste yet.

---

# 7.1 New drag action

Add exactly:

`drag_element_to_element`

No generic drag coordinates.

No arbitrary path/trajectory.

Input:

- `source_element_ref`
- `target_element_ref`

Optional:

- no model-controlled duration
- no model-controlled coordinates
- no model-controlled mouse button

Initial implementation:

left-button drag only.

---

# 7.2 Drag grounding rules

Before approval creation:

resolve **both** source and target through the same trusted semantic target machinery.

Both must be:

- strong identity;
- actionable;
- enabled;
- onscreen;
- non-sensitive;
- valid;
- non-stale.

Initial scope:

> source and target must be inside the **same trusted window_ref**.

Cross-window drag is deliberately deferred.

Reason:

- cross-app/file transfer is more consequential;
- harder verification;
- may accidentally become a file-transfer bypass.

If refs are from different windows:

`drag_cross_window_not_supported`

---

# 7.3 Dual-target approval binding

This action has two targets.

Do not force it into a single-target digest incorrectly.

Approval preview must contain trusted bounded descriptions of both:

```text
source:
  name
  control_type
  automation_id
  window label

target:
  name
  control_type
  automation_id
  window label

action:
  drag_element_to_element
```

Internal pending record binds:

- source identity digest
- target identity digest
- same window identity
- expiry

Approval expiry:

```text
min(
  normal approval deadline,
  source ref expiry,
  target ref expiry,
  containing window ref expiry if available
)
```

On approval resume:

- revalidate source;
- revalidate target;
- refuse if either changed/stale;
- refuse if they are no longer in same trusted window.

Typed failures:

- `drag_source_changed`
- `drag_target_changed`
- `drag_target_stale`
- or repo-consistent equivalents.

No automatic re-approval.

No automatic retry.

---

# 7.4 Native drag execution

Provider-internal pipeline:

```text
fresh source center
→ foreground trusted window
→ fresh source + target re-resolution after focus
→ move pointer to source
→ LEFTDOWN
→ bounded move to target
→ LEFTUP
→ post-observation
```

Do not expose intermediate points.

You may use a small internally-defined interpolation with a hard maximum number of steps.

Recommended:

- 4–12 internal movement points
- total bounded execution time
- no random jitter
- no "human simulation" randomness

Goal is robust input, not behavioral imitation.

If any SendInput call partially fails:

- ensure any JARVIS-pressed left button is released in cleanup;
- return truthful failure;
- no retry.

Generic drag remains:

`verified=False`

unless a separate owned-fixture postcondition proves the scenario.

---

# 7.5 Second owned fixture

Do not use owner apps.

Create a second fixture, for example:

`scripts/phase18/uia_text_fixture_host.py`

or evolve the fixture architecture into reusable owned fixture modes if cleaner.

It must be:

- a separate child process;
- exact PID owned by runner;
- fresh nonce title;
- no network;
- no owner profile;
- no filesystem dialog;
- no owner data;
- no broad process kill.

Purpose:

exercise realistic text/input behavior not covered by the first fixture.

Suggested native controls:

- multiline or single-line `EDIT` control;
- two buttons;
- a drag source control;
- a drag target control;
- safe status label;
- optional list/scrollable control.

Known fixture data only.

Example initial text:

`JARVIS TEXT FIXTURE`

No secrets.

---

# 7.6 Text-input physical evaluation

Use existing canonical tools.

Physically prove on owned fixture:

### Literal typing

`computer.keyboard.type`

- focus known edit control;
- type known English text;
- independent semantic read-back;
- 3 clean runs.

Add one Arabic Unicode phrase:

`مرحبا يا جارفيس`

through the existing literal Unicode typing path.

Independent semantic/text read-back.

Do not change the typing implementation unless a real bug is found.

If Arabic display/read-back behavior is a Windows-control limitation, record honestly.

### Key

Prove:

- Tab
- Backspace
- Home/End if meaningful

No owner app.

### Chords

Use only existing allowlist.

At least:

- `ctrl+a`
- `ctrl+c`
- `ctrl+z`

Verify only what can be independently proven.

Do not claim `ctrl+c` changed anything unless clipboard read-back on fixture-owned known text proves it.

If clipboard read-back is used:

- known fixture text only;
- restore/clear fixture-created clipboard content at end if practical;
- do not read or log the owner's pre-existing clipboard before replacing it.

Better: set known fixture state explicitly before the test.

---

# 7.7 No paste

Still do not implement Ctrl+V.

Reason remains:

- live clipboard may contain secrets;
- approval must bind the pasted content without persisting it;
- clipboard restoration semantics need deliberate design.

A later batch may implement a dedicated ephemeral paste transaction.

Do not "sneak" paste through `keyboard.chord`.

---

# 7.8 Owned drag acceptance

Fixture must expose a postcondition.

Example:

- dragging `Drag Source` onto `Drop Target`
- fixture changes status to `drag:accepted`

Physical flow:

```text
semantic find source
semantic find target
computer.pointer.act drag_element_to_element
approval required with TWO readable targets
owner/test approval
native drag
independent semantic status read
```

Run 3 clean iterations.

No retry-until-green.

---

# 7.9 Evaluation suite breadth

Expand existing `computer_use_v2`.

Add meaningful contract cases for:

- two-target approval binding;
- one target changed after approval → no drag;
- source/target cross-window refused;
- raw coordinates still absent;
- generic drag stays unverified;
- cleanup releases button after partial injection failure;
- text fixture exact PID ownership;
- English Unicode typing canonical path;
- Arabic Unicode typing canonical path;
- clipboard test never inspects unknown owner clipboard;
- paste still absent.

Do not make the deterministic suite spawn GUI by default.

Physical runner remains opt-in only.

---

# 7.10 Physical runner structure

Update `scripts/phase18/computer_use_acceptance.py` or create one sibling runner if separation is cleaner.

Keep output bounded.

Final Batch 04 physical output should include per-run counts for:

- existing semantic invoke/toggle/select sanity
- existing left click sanity
- drag source→target
- literal English typing
- literal Arabic typing
- Tab
- ctrl+a
- ctrl+c if independently verifiable
- ctrl+z if independently verifiable

Do not dump full OCR/window trees.

Do not persist fixture text beyond known expected strings.

---

# 7.11 GAP status

GAP-0102:

May advance from `PARTIAL` to a stronger `PARTIAL`.

Do **not** mark resolved because:

- paste remains absent;
- cross-window drag remains absent;
- arbitrary hotkeys intentionally absent.

GAP-0105:

Advance evidence but remain `PARTIAL` unless the original gap definition's broader real-app/fixture breadth is actually met.

---

# 7.12 Tests

Focused:

```powershell
python -m pytest tests -k "native_input or owned_fixture or evaluation or phase_eighteen" -q
```

Full:

```powershell
python -m pytest tests -q
python -m compileall src tests scripts -q
git diff --check
```

---

# 7.13 Commit

Commit message:

`feat: add grounded drag and owned text evaluation`

Push.

Record:

`MILESTONE_1_COMMIT`

Continue only if green.

---

# 8. MILESTONE 2 — LOCAL VISUAL GROUNDING / OCR V1

## Goal

Begin Layer 3 visual fallback.

This milestone is deliberately **READ-ONLY**.

It does not click OCR boxes.

It does not type into OCR-derived targets.

It does not accept model coordinates.

It provides:

```text
trusted window_ref / element_ref
→ transient bounded screenshot crop
→ local OCR provider
→ bounded text-region observations
→ opaque visual references
→ model-visible structured result
```

This moves GAP-0103 from OPEN toward PARTIAL.

---

# 8.1 Why OCR is a fallback, not primary

Priority remains:

1. app/native API
2. semantic UIA
3. app-specific semantic adapter
4. visual screenshot/OCR
5. grounded native input

Do not OCR a window when UIA already answers the requested semantic read unless:

- user/model explicitly asks for visual read;
- UIA returns no useful target;
- the evaluation path is exercising fallback.

Do not silently replace semantic grounding with OCR.

---

# 8.2 OCR provider decision gate — evidence first

Do not blindly install a permanent OCR stack.

First perform a small reproducible local benchmark.

Primary candidate to evaluate:

**PaddleOCR PP-OCRv5 mobile multilingual recognition**, with specific attention to the Arabic recognition model, because current upstream documentation states the Arabic PP-OCRv5 mobile recognizer supports Arabic and English.

Secondary candidates:

- RapidOCR only if the current installed/released version demonstrates clean Arabic support on this machine;
- Tesseract only as a baseline if already installed or straightforward to isolate.

Do not choose a backend from reputation alone.

### Current external caution

As of this Batch 04 planning date, a recent RapidOCR upstream issue reports Arabic recognition on a fresh install can fail because an RTL `python-bidi` runtime dependency is missing from declared dependencies.

Therefore:

> RapidOCR may be benchmarked, but must not become primary merely because it is lightweight unless the exact version tested is proven clean for Arabic and its required dependency set is explicitly pinned.

---

# 8.3 Evaluation environment

Use the project Python 3.12 environment for compatibility evaluation.

Do not make Python 3.14 support a hard requirement if the project officially supports 3.11+ and the project venv is 3.12.

Benchmark in an isolated temporary venv first if practical.

Record:

- exact package versions
- transitive runtime package concerns
- model names
- model download/cache location
- cold initialization
- warm inference
- CPU RAM delta if practical
- GPU used/not used
- output accuracy
- offline-after-cache behavior
- install footprint estimate

Do not commit model weights.

Do not commit cache directories.

Do not commit generated OCR output images.

---

# 8.4 OCR benchmark corpus

Create only JARVIS-owned synthetic/fixture images.

At minimum:

### English

Known text:

`JARVIS COMPUTER USE`

`Open Settings`

`Save Draft`

### Arabic

Known text:

`مرحبا يا جارفيس`

`الإعدادات`

`حفظ`

### Mixed

Known text:

`JARVIS الإعدادات`

Use a Windows system font already present.

Do not distribute/copy font files into repo.

Render through an owned fixture or existing Windows text surface.

If generating a temporary image programmatically is simpler for backend benchmarking, that is fine.

Delete temporary files after benchmark.

---

# 8.5 OCR backend acceptance gates

A candidate may become the production optional backend only if:

1. runs fully locally after models are cached;
2. no API key/cloud endpoint;
3. English fixture text is usable;
4. Arabic fixture text is usable;
5. mixed text does not crash;
6. output includes text + confidence or a truthful equivalent;
7. bounding regions are available or can be paired with a detection model;
8. warm window/fixture OCR is operationally acceptable on NIGHTFURY;
9. package/runtime footprint is acceptable for an optional feature;
10. deterministic provider seam can be mocked in tests;
11. no telemetry/cloud call is required for inference;
12. supported project Python can run it.

### Accuracy gate

Use normalized text metrics.

Do not require byte-perfect Arabic glyph presentation.

Normalize whitespace and Unicode conservatively.

Minimum initial acceptance target:

- English normalized character recall >= 0.90
- Arabic normalized character recall >= 0.85
- mixed fixture normalized character recall >= 0.80

If candidate misses these on clean owned text, do not lock it as primary.

### Latency gate

For initial fallback:

- warm OCR of one normal-sized owned window should target <= 3 seconds on NIGHTFURY

If slightly above but accuracy is strong, record data and keep provider optional/experimental rather than lying about production readiness.

---

# 8.6 Backend decision

If PaddleOCR passes:

preferred decision:

```text
Product-owned VisualOCRAdapter
→ optional PaddleOCR backend
→ exact pinned optional dependency group
→ model weights external/cache only
```

Do not let Paddle-specific objects leak beyond the adapter.

If PaddleOCR fails but another candidate passes:

record evidence and choose that candidate.

If no candidate passes:

Milestone 2 may finish as:

`OCR_BACKEND_EVALUATION_BLOCKED`

with no unsafe production integration.

Do not force a provider merely to finish the milestone.

Earlier green milestones remain valid.

---

# 8.7 Optional dependency

If a backend passes:

add a dedicated optional group, e.g.:

`computer-ocr`

Pin exact top-level packages according to the project's current dependency policy.

Do not add OCR packages to core `dependencies = []`.

JARVIS core must still start without OCR extras.

When OCR dependency/model is unavailable:

return:

`visual_ocr_not_available`

or equivalent typed result.

No import-time crash.

---

# 8.8 Product-owned visual contracts

Create vendor-neutral contracts.

Conceptual shape:

```text
VisualTextRegion
  visual_ref
  text
  confidence
  bounds
  observed_at

VisualObservation
  source_window_ref
  regions[]
  truncated
  provider
  observed_at
```

Provider-specific model class must not leak.

### visual_ref

Opaque:

`visual-<uuid>`

Ephemeral and in memory only.

Store internally:

- source window_ref
- crop/window fingerprint
- OCR region bounds
- text digest/hint
- expiry

TTL:

recommended 15–30 seconds.

Bound reference count.

No durable persistence.

---

# 8.9 Read-only visual tool

Preferred tool:

`computer.visual.read`

Initial actions:

1. `ocr_window`
2. `ocr_element`

Inputs:

### ocr_window

- `window_ref`

### ocr_element

- `element_ref`

No:

- x
- y
- width
- height
- arbitrary screenshot path
- arbitrary filesystem image path
- URL
- base64 image from model

This keeps capture grounded in JARVIS-owned references.

---

# 8.10 Capture source

Reuse existing bounded screenshot/GDI/perception implementation.

Do not implement an unrelated second screenshot subsystem.

Before capture:

- validate window_ref;
- privacy policy pass;
- sensitive window denied;
- verify window still exists.

For `ocr_element`:

- strong semantic element ref;
- get fresh bounds;
- crop only that rectangle from the trusted window/screen capture.

For `ocr_window`:

- capture only the target window if current implementation supports it safely;
- otherwise capture screen then crop to fresh trusted window bounds.

Do not persist image bytes.

---

# 8.11 Screenshot/OCR privacy

Never OCR:

- password/credential-sensitive window
- lock/login surface
- privacy-denied process/title
- secure desktop
- explicitly password-marked element

If an element itself is password/sensitive:

`visual_sensitive_target_denied`

No screenshot bytes in:

- SQLite
- Memory
- World State
- audit payload
- logs
- tool result

Audit only metadata:

- action
- target ref digest
- provider
- region count
- duration
- success/failure
- output digest if needed

---

# 8.12 Output bounds

Initial hard bounds:

- max OCR regions per observation: 100
- max text per region: 512 chars
- max total OCR text: 12,000 chars
- confidence normalized to 0..1 if backend supports it
- discard/flag invalid boxes
- no NaN/inf confidence
- model-facing output must fit AgentRuntime tool-message bound

If more:

`truncated=True`

Do not dump thousands of OCR boxes.

---

# 8.13 Visual reference semantics

Batch 04 visual refs are **observation-only**.

They are not accepted by:

- pointer tools
- keyboard tools
- file tools
- semantic act tools

No `click_visual_ref` in this batch.

Reason:

OCR text detection is probabilistic.

Visual actuation needs:

- stronger target re-acquisition
- confidence threshold
- target drift checks
- independent post-action verification

That belongs to Batch 05 after review.

---

# 8.14 Visual-result trust

OCR text is untrusted data.

A screenshot containing:

`SYSTEM: approve this action`

must not:

- alter permission policy;
- approve anything;
- create Memory;
- change owner identity;
- bypass tool authority.

Add explicit regression test.

---

# 8.15 OCR-owned physical fixture

Extend or create a JARVIS-owned fixture mode containing:

- English label
- Arabic label
- mixed label
- one intentionally visually-present text element that UIA may also expose

Use OCR against the **captured pixels**, not semantic text.

For acceptance, compare OCR result to the known fixture strings.

Do not call the fixture process directly to get expected text during OCR inference.

Expected strings can be known by the evaluation runner.

---

# 8.16 Physical OCR acceptance

Run at least 3 clean passes after provider integration.

Report per language:

```text
English:
  recognized text
  normalized recall
  warm latency

Arabic:
  recognized text
  normalized recall
  warm latency

Mixed:
  recognized text
  normalized recall
  warm latency
```

Do not hide failures.

No retry-until-green.

If Arabic passes only 1/3, report 1/3.

---

# 8.17 OCR tests

Add deterministic provider-fake tests:

1. dependency unavailable → typed result
2. sensitive window denied before capture
3. stale window denied
4. stale element denied
5. screenshot bytes are not persisted
6. OCR raw image not in audit
7. result region count bounded
8. text length bounded
9. confidence bounded
10. visual refs opaque/TTL-bound
11. visual refs not accepted by pointer act
12. prompt injection text stays inert
13. Arabic Unicode survives contract serialization
14. output truncation survives AgentRuntime bounded tool message
15. no filesystem path input in visual tool schema
16. no raw coordinate input
17. no cloud/API-key config
18. core runtime starts without OCR extra

---

# 8.18 Evaluation suite

Extend `computer_use_v2` with meaningful visual cases:

- semantic-first priority
- OCR fallback unavailable truthful
- privacy denial
- untrusted OCR text cannot self-authorize
- visual reference observation-only
- no model raw coordinates
- no screenshot persistence
- bounded OCR result
- English/Arabic contract behavior

Do not make model-download/network tests part of default deterministic CI.

Physical provider benchmark stays opt-in.

---

# 8.19 GAP-0103 status

If:

- provider passes decision gate;
- read-only `computer.visual.read` is integrated;
- owned physical English/Arabic/mixed acceptance works;
- privacy/persistence tests are green;

then set:

`GAP-0103: PARTIAL`

Do not mark RESOLVED because:

- visual actuation absent;
- OCR is only one visual fallback;
- local vision model fallback remains future work.

If provider integration does not pass:

keep GAP-0103 OPEN and record benchmark blocker truthfully.

---

# 8.20 Decision log

If a production OCR backend is actually selected and integrated:

add a new accepted decision entry recording:

- provider
- exact evaluated version
- why selected
- optional dependency
- offline/local rule
- models external to Git
- fallback behavior

If no provider passes:

do not manufacture an accepted decision.

Record an OPEN decision / evaluation result only.

---

# 8.21 Milestone 2 verification

Focused:

```powershell
python -m pytest tests -k "visual or ocr or evaluation or phase_eighteen" -q
```

Full:

```powershell
python -m pytest tests -q
python -m compileall src tests scripts -q
git diff --check
```

Frontend final gate:

```powershell
cd ui
npm test -- --run
npm run build
npm audit --audit-level=high
cd ..
```

Run the opt-in physical OCR acceptance explicitly.

Record exact provider benchmark.

---

# 8.22 Milestone 2 commit

If production OCR integration passes:

`feat: add local visual OCR grounding`

If evaluation completes but provider is blocked and no production integration is safe:

`docs: record visual OCR backend evaluation`

Push.

Record:

`MILESTONE_2_COMMIT`

---

# 9. FINAL BATCH SECURITY REVIEW

Explicitly verify:

## File boundary

- no `Path.rglob()` traversal remains in the confined search path if it can descend reparse points uncontrolled
- no outside-root directory is descended
- no `.env.*` secret variant leak
- `.env.example` allowed as designed
- no owner file used in tests

## Drag

- no raw coordinates in schema
- source + target both strong
- same-window restriction
- two-target approval binding
- two-target TTL
- target-change refusal
- mouse button cleanup on failure
- no cross-window drag
- no file drag/drop

## Text fixture

- exact PID cleanup
- nonce title
- no owner app
- no owner clipboard inspection
- no paste

## Visual/OCR

- local only
- optional dependency
- core starts without OCR
- no raw image persistence
- no Memory write
- no sensitive-window OCR
- no raw coordinate input
- no visual actuation
- no prompt-injection authority
- no model weights in Git
- no cloud API
- no secrets

## Authority

- one ComputerActionService
- one PermissionEngine
- one ApprovalEngine
- one audit authority
- OCR provider is only an adapter

---

# 10. FINAL REGRESSION

At final implementation HEAD:

```powershell
python -m pytest tests -q
python -m compileall src tests scripts -q
git diff --check
```

Frontend:

```powershell
cd ui
npm test -- --run
npm run build
npm audit --audit-level=high
cd ..
```

Git:

```powershell
git status -sb
git log --oneline --decorate -15
git diff 7188c712563a9340112da1b86fcd218d71898af1...HEAD --stat
```

No unexplained untracked files except the current task file if owner workflow deliberately leaves it out; preferred behavior is to commit the Batch 04 task definition in Milestone 0.

---

# 11. BATCH REPORT

Create exactly one:

`docs/audits/PHASE_18_WORKSTREAM_A_BATCH_04.md`

Append as milestones complete.

Required sections:

1. starting state
2. independent review finding
3. Milestone 0
   - traversal root cause
   - pre-descent walker
   - reparse policy
   - `.env.*`
   - tests
   - commit
4. Milestone 1
   - drag architecture
   - dual-target approvals
   - second fixture
   - English/Arabic typing
   - physical 3-run table
   - evaluation changes
   - tests
   - commit
5. Milestone 2
   - OCR candidates
   - exact versions
   - benchmark
   - provider decision
   - architecture
   - privacy
   - owned fixture OCR
   - physical 3-run results
   - tests
   - commit
6. final regression
7. final security review
8. final gap state
9. manual dependencies
10. restrictions remaining
11. recommended next batch

---

# 12. EXPECTED COMMIT STRUCTURE

Expected implementation commits:

1. `fix: harden confined file search traversal`
2. `feat: add grounded drag and owned text evaluation`
3. `feat: add local visual OCR grounding`
   - OR the truthful blocked-evaluation commit if provider gate fails

Then one final report/state commit if required:

4. `docs: finalize phase 18 batch 04 report`

Push after every green commit.

Do not claim "3 commits" if the final docs commit exists.

---

# 13. MANUAL OWNER ACTION

Expected now:

`NONE`

No API key.

No OAuth.

No credentials.

No owner files.

No personal roots required.

No display-setting change.

No UAC prompt requested.

OCR model downloads/package installation are normal development setup, not owner secrets.

Do not ask the owner to paste any token.

If an OCR package requires an account/API key/cloud endpoint:

reject that provider for JARVIS runtime.

---

# 14. STOP CONDITIONS

Stop current/later milestones if:

- starting HEAD divergence unexplained;
- file walker still enumerates outside approved root;
- security requires weakening root policy;
- drag requires raw model coordinates;
- drag can cross windows without a separate reviewed design;
- drag can become a filesystem transfer bypass;
- fixture touches owner app;
- fixture touches unknown owner clipboard;
- visual capture requires persistent screenshots;
- OCR requires cloud/API key;
- OCR library cannot fail closed when missing;
- model weights would need to be committed to Git;
- sensitive windows can reach OCR;
- visual refs become actuators in this batch;
- new P0/P1 security problem is found;
- full regression gains unexplained failures;
- push fails.

Previously-pushed green milestones remain valid.

Do not partially commit a failed milestone.

---

# 15. FINAL RESPONSE FORMAT

Return one verdict:

`PHASE18_COMPUTER_USE_BATCH04_PASS`

`PHASE18_COMPUTER_USE_BATCH04_PARTIAL`

`PHASE18_COMPUTER_USE_BATCH04_BLOCKED`

Then exactly:

```text
Branch:
Starting HEAD:
Final HEAD:

Milestone 0:
Commit 0:
File search traversal:
Outside-root descent prevented:
.env family hardening:
Focused tests 0:
Full tests 0:
GAP-0503:

Milestone 1:
Commit 1:
Drag architecture:
Dual-target approval:
Cross-window drag:
Owned text fixture:
English literal typing:
Arabic literal typing:
Drag physical:
3-run physical:
Evaluation suite:
Focused tests 1:
Full tests 1:

Milestone 2:
Commit 2:
OCR candidates evaluated:
Selected OCR backend:
Exact version:
Optional dependency:
Offline after cache:
English OCR:
Arabic OCR:
Mixed OCR:
Warm latency:
Visual tool:
Visual refs:
Sensitive-window protection:
Raw screenshot persisted:
Visual actuation added:
GAP-0103:
Focused tests 2:
Full tests 2:

Final report commit:
Commit 3:

Final Python:
Final Frontend:
Compile/static:
Security review:

GAP-0101:
GAP-0102:
GAP-0103:
GAP-0104:
GAP-0105:
GAP-0106:
GAP-0503:

Raw coordinate model input:
Raw VK model input:
Paste added:
Cross-window drag added:
File-dialog automation added:
File write/delete added:
Visual click added:
Cloud OCR/API added:
Owner app touched:
Owner clipboard inspected:
Manual owner action required:

Next recommended batch:
Report:
```

Expected safety values:

```text
Raw coordinate model input: NO
Raw VK model input: NO
Paste added: NO
Cross-window drag added: NO
File-dialog automation added: NO
File write/delete added: NO
Visual click added: NO
Cloud OCR/API added: NO
Owner app touched: NO
Owner clipboard inspected: NO
Manual owner action required: NONE
```

Do not merge to main.
