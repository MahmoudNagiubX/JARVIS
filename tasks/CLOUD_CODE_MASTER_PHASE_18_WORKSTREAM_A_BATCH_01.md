# CLOUD CODE MASTER TASK — PHASE 18 WORKSTREAM A BATCH 01
# CHECKPOINT REVIEW → SEMANTIC UIA FOUNDATION → JARVIS READ TOOLS → BOUNDED SEMANTIC ACTIONS

**Project:** JARVIS  
**Target agent:** Cloud Code  
**Owner:** Mahmoud  
**Date:** 2026-09-12  
**Execution style:** One detailed master task containing sequential milestones.  
**Git rule:** Each milestone must be independently verified, committed, and pushed before continuing to the next milestone.

---

# 0. PURPOSE

You are starting with **zero prior session knowledge**.

The owner explicitly does **not** want one tiny Cloud Code session per micro-step.

Instead, this single master task contains several bounded milestones. You must execute them in order.

For every milestone:

```text
READ ONLY WHAT THAT MILESTONE NEEDS
→ IMPLEMENT ONLY THAT MILESTONE
→ RUN FOCUSED TESTS
→ RUN ITS REQUIRED REGRESSIONS
→ INSPECT DIFF
→ COMMIT
→ PUSH THE SAME FEATURE BRANCH
→ CONTINUE TO NEXT MILESTONE ONLY IF GREEN
```

Do not combine unfinished milestones into one commit.

Do not continue after a milestone fails.

Do not merge to `main`.

The goal of this batch is to make **meaningful Computer Use V2 progress in one Cloud Code session** without turning it into one giant unsafe change.

---

# 1. CURRENT VERIFIED BASELINE

Repository:

`MahmoudNagiubX/JARVIS`

Expected local repo:

`C:\Jarivs\00_final\jarvis`

Expected branch:

`feature/phase-18-computer-use-v2`

Expected branch HEAD before this batch:

`4ca89820d550798223b4691e9b3b077e9388830e`

Current branch is expected to be exactly two commits ahead of `main`:

1. `00f2bc23af4fc84e413bd5825748e0c3552ffff0`
   - `fix: close phase 18 stabilization gate`
2. `4ca89820d550798223b4691e9b3b077e9388830e`
   - `docs: record phase 18 UIA backend evaluation`

Do not assume this blindly.

Run first:

```powershell
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git status --short
git log --oneline --decorate -5
git remote -v
```

If HEAD differs because an owner-approved commit already landed, inspect it before proceeding.

If HEAD differs for an unexplained reason, STOP.

Do not reset, stash, clean, checkout away, or discard owner changes.

---

# 2. VERY SMALL MANDATORY READ SET

Do **not** read the full repo or all old phase files.

Read these first:

1. `AGENTS.md`
2. `docs/source_of_truth/01_JARVIS_CORE_SOURCE_OF_TRUTH.md`
3. `docs/source_of_truth/03_JARVIS_GAP_REGISTER.md`
4. `docs/source_of_truth/04_JARVIS_EXECUTION_ROADMAP.md`
5. `docs/source_of_truth/05_JARVIS_DECISION_LOG.md`
6. `docs/audits/PHASE_18A2_STABILIZATION.md`
7. `docs/audits/PHASE_18_WORKSTREAM_A1_UIA_BACKEND_EVALUATION.md`
8. `docs/audits/PHASE_18_GIT_CHECKPOINT.md`

Then inspect only these code areas before Milestone 1/2:

- `src/jarvis/perception/windows.py`
- `src/jarvis/perception/privacy.py`
- `src/jarvis/computer/service.py`
- `src/jarvis/computer/controller.py`
- `src/jarvis/tools/registry.py`
- `src/jarvis/tools/service.py`
- `src/jarvis/agents/runtime/runtime.py`
- `src/jarvis/bootstrap.py`
- `src/jarvis/contracts.py`
- `pyproject.toml`

Tests:

- `tests/test_phase_eighteen_stabilization.py`
- `tests/test_phase_ten_active_perception.py`
- `tests/test_phase_eleven_windows_interaction.py`
- any directly-related computer/tool tests discovered from references/imports

Only expand this read set when a concrete dependency in the code requires it.

---

# 3. LOCKED ARCHITECTURE FOR THIS BATCH

Preserve:

```text
request
→ AgentRuntime
→ ToolExecutionService / canonical tool path
→ PermissionEngine
→ ApprovalEngine when required
→ ComputerActionService
→ product-owned semantic UI adapter
→ Windows UIA provider
→ re-observe / verify
→ typed result with verified=True/False/None
→ audit/event
→ model/user
```

Never create:

- `ComputerActionServiceV2`
- second permission engine
- second approval engine
- second audit path
- alternate model-to-UIA direct path
- alternate raw HWND model tool
- general-purpose shell automation service
- unrestricted COM/UIA escape hatch

### Computer Use order remains

```text
native/domain API
→ semantic Windows UIA
→ app-specific semantic adapters
→ visual grounding
→ bounded native input
→ PyAutoGUI compatibility fallback
```

This batch covers primarily the **UIA semantic layer**.

---

# 4. EXISTING WINDOW REFERENCE AUTHORITY — REUSE IT

Current `WindowsDesktopProvider` already has:

- opaque JARVIS-issued `window-<uuid>` refs;
- TTL;
- bounded in-memory ref store;
- HWND hidden internally;
- process/title/class fingerprinting;
- stale-reference validation;
- privacy checks;
- foreground/input validation.

Current defaults include:

- window-ref TTL around 45 seconds;
- bounded reference count.

**Do not create a second independent top-level window-reference system.**

The new semantic layer should use/extend the existing product-owned window refs.

An element reference may be new, but must be:

- opaque;
- ephemeral;
- tied to an existing window ref;
- bounded in count;
- TTL-bound;
- provider-private internally;
- revalidated before every later actuation;
- never a raw COM object, RuntimeId, HWND, coordinate, or selector exposed directly to the model.

---

# 5. A1 BACKEND EVALUATION — ACCEPTED DIRECTION

The A1 evaluation on NIGHTFURY found:

### Production backend recommendation

Product-owned adapter around:

- `uiautomation`
- `comtypes` underneath

embedded **in-process**.

Measured warm calls were roughly 10–50 ms after initialization.

### Optional developer/evaluation tool

Microsoft `winapp ui`.

Useful for:

- developer inspection;
- future CI/evaluation;
- cross-checking stale-target behavior.

But it should **not** become the production agent-loop backend because:

- process per call;
- roughly 250–350 ms repeated cost;
- machine-level distribution/versioning;
- telemetry by default unless disabled;
- weaker product-owned unit-test seam.

### Do not use as primary in this batch

- `pywinauto`
- custom COM bindings from scratch
- PyAutoGUI

Milestone 0 below records this as the accepted decision.

---

# 6. GLOBAL SECURITY / PRODUCT CONSTRAINTS

All milestones must preserve:

- local-first;
- offline after dependencies are installed;
- free runtime;
- no API key;
- no cloud computer-use service;
- no raw secrets in logs/audit/docs;
- no unrestricted shell;
- no elevation/UAC bypass;
- no arbitrary filesystem authority expansion;
- browser/research content remains untrusted;
- UI text is observation/data, never system authority;
- semantic UI text cannot grant JARVIS permissions;
- sensitive windows must be denied using existing privacy policy;
- no screen/OCR persistence introduced;
- no owner-document mutation during acceptance testing;
- no interaction with real personal chat/email/payment/admin/security windows;
- no physical success claims from mocks alone.

---

# 7. CRITICAL CARRY-FORWARD RESTRICTION — GAP-0503

F18A1-010 / GAP-0503 remains open.

Existing file actions have insufficient approved-root/sensitive-path confinement.

Therefore this entire batch must NOT:

- widen `inspect_file`;
- widen `search_files`;
- widen `open_file`;
- widen `open_folder`;
- introduce semantic file-picker automation;
- set path values in file dialogs;
- invoke Open/Save dialogs to access arbitrary paths;
- use UIA as a backdoor around file permissions.

If a UIA tree includes a file dialog, you may inspect its metadata in a test only if safe, but **do not interact with path controls or confirm file operations**.

---

# 8. MILESTONE 0 — CHECKPOINT REVIEW CORRECTIONS + BACKEND DECISION LOCK

## Goal

Close the independent review findings before building on top of the checkpoint.

This milestone contains:

1. Home Assistant brightness verification correction;
2. stale active-work documentation correction;
3. formal decision lock for the UIA backend;
4. clean checkpoint commit.

Do not implement semantic UIA yet in Milestone 0.

---

## 8.1 Fix Home Assistant brightness verification

File:

`src/jarvis/devices/home/service.py`

Current behavior:

- action contract uses brightness percentage 0–100;
- service writes Home Assistant `brightness_pct`;
- verification currently expects a `brightness_pct` state attribute.

Home Assistant's light state normally exposes:

`attributes["brightness"]`

on the 0–255 scale.

Required behavior:

```text
desired_pct = action percentage
expected_255 = round(desired_pct * 255 / 100)
actual = state.attributes["brightness"]
verified = abs(actual - expected_255) <= 1
```

Rules:

- keep JARVIS public contract as 0–100;
- keep POST using `brightness_pct`;
- state verification uses numeric `brightness`;
- tolerance max ±1;
- missing brightness => false;
- invalid/non-numeric => false;
- materially wrong value => false;
- do not turn uncertainty into true.

Required focused tests:

- 50% + actual brightness 128 => true
- 50% + clearly wrong brightness => false
- missing brightness => false
- invalid brightness type => false
- provider/read-back failure still cannot produce verified true

Do not modify unrelated Home behavior.

---

## 8.2 Correct AGENTS active-work state

`AGENTS.md` should no longer say Phase 18A is the current gate.

Keep it short.

Current truth:

- 18A.1 complete
- 18A.2 complete
- A1 backend evaluation complete
- active program = Phase 18 Workstream A / Computer Use V2
- this batch now advances the semantic UIA foundation

Do not duplicate roadmap detail.

---

## 8.3 Record the accepted UIA decision

Update:

`docs/source_of_truth/05_JARVIS_DECISION_LOG.md`

Create the next accepted decision, expected:

`DEC-046`

Meaning:

> Computer Use V2 semantic Windows control uses a product-owned in-process Python UIA adapter based on `uiautomation`/`comtypes`. Microsoft `winapp ui` remains optional developer/evaluation tooling and is not a production runtime dependency.

Status:

`ACCEPTED_2026-09-12`

Evidence summary:

- A1 real NIGHTFURY evaluation;
- warm in-process performance;
- package pinning;
- Python testability/mockability;
- winapp stronger dev inspection/staleness ergonomics but higher repeated call overhead and preview/tooling concerns.

Keep DEC-018 as historical candidate evaluation context, but point to DEC-046.

Resolve/remove `OPEN-001` from unresolved decisions by marking it resolved by DEC-046.

Do not modify unrelated decisions.

---

## 8.4 Minimal roadmap/gap update

Update only:

- `03_JARVIS_GAP_REGISTER.md`
- `04_JARVIS_EXECUTION_ROADMAP.md`

Required truth:

- backend-selection subproblem resolved;
- GAP-0101 remains open until semantic capability is implemented;
- A1 evaluation complete;
- semantic UIA implementation is now active;
- GAP-0503 remains open.

---

## 8.5 Milestone 0 verification

Run:

```powershell
python -m pytest tests/test_phase_eighteen_stabilization.py -q
python -m pytest tests -q
python -m compileall src tests -q
git diff --check
```

Frontend:

```powershell
cd ui
npm test
npm run build
npm audit --audit-level=high
cd ..
```

No unexplained failure permitted.

---

## 8.6 Milestone 0 report

Create or begin the batch report:

`docs/audits/PHASE_18_WORKSTREAM_A_BATCH_01.md`

Record Milestone 0 findings/results.

This one report should accumulate evidence for all milestones in this master task.

Do not create four separate audit reports.

---

## 8.7 Milestone 0 commit + push

Commit message:

`fix: close phase 18 checkpoint review`

Stage explicitly.

Include the previously-untracked checkpoint task definition if present:

`tasks/CLOUD_CODE_TASK_PHASE_18_GIT_CHECKPOINT_COMMIT_PUSH.md`

Include this master task file too:

`tasks/CLOUD_CODE_MASTER_PHASE_18_WORKSTREAM_A_BATCH_01.md`

or the exact filename the owner saved it under.

Push:

```powershell
git push origin feature/phase-18-computer-use-v2
```

Record SHA as:

`MILESTONE_0_COMMIT`

Only continue if push succeeds and worktree is suitable for Milestone 1.

---

# 9. MILESTONE 1 — PRODUCT-OWNED SEMANTIC UIA FOUNDATION

## Goal

Implement the first real Computer Use V2 semantic backend.

This milestone is **read-only**.

No semantic actuation yet.

---

## 9.1 Dependency

Add a dedicated optional dependency group to `pyproject.toml`.

Preferred shape:

```toml
[project.optional-dependencies]
computer-uia = [
  "uiautomation==2.0.29"
]
```

Before editing, inspect existing optional dependency style and follow it.

Do not add `pywinauto`.

Do not add `winapp`.

Do not manually list `comtypes` if the selected pinned `uiautomation` dependency already owns the correct dependency relationship unless reproducibility evidence requires an explicit compatible pin.

Avoid over-pinning transitive packages without evidence.

### Runtime rule

JARVIS core must still import/start without `computer-uia` installed.

The semantic provider must degrade truthfully, e.g.:

`uia_not_available`

It must not crash bootstrap.

---

# 9.2 Product-owned semantic adapter

Implement one product-owned adapter/provider.

Choose location based on existing structure after inspection.

Preferred conceptual placement:

`src/jarvis/computer/semantic_uia.py`

or a similarly clear module.

Do not create a second service authority.

Possible product-owned protocol/interface:

`SemanticDesktopAdapter`

Possible concrete implementation:

`WindowsUIAutomationAdapter`

Names may differ if repo conventions make another name clearly better.

The third-party `uiautomation` package must remain **behind** this adapter.

No raw third-party objects leave it.

---

# 9.3 Product-owned models

Create small normalized models/dataclasses for semantic observations.

Keep them product-owned and vendor-neutral.

Minimum conceptual data:

### SemanticElementSnapshot

- element_ref
- window_ref
- name
- control_type
- automation_id
- enabled
- offscreen
- focused
- focusable
- bounds
- supported_patterns
- text/value when safely retrievable and bounded
- observed_at
- confidence / provider metadata only if existing contracts make this appropriate

### Element reference internal record

Must include enough provider-private identity hints to re-resolve:

- parent window ref
- AutomationId if available
- control type
- name hint
- bounded ancestry/path hints
- runtime identity digest or equivalent provider-private hint
- expiry
- observation time

The model sees only the opaque element ref and normalized safe properties.

No raw RuntimeId.

No raw COM pointer.

No raw HWND.

No coordinates as action identity.

Bounds may be returned as observation metadata but **not used as primary target identity**.

---

# 9.4 Reference store

Element refs must be:

- `element-<uuid>` or consistent product-owned opaque IDs;
- in memory;
- ephemeral;
- TTL bounded;
- count bounded;
- tied to a valid existing `window_ref`.

Recommended defaults:

- TTL roughly aligned with existing 30–60 second window-ref policy;
- max refs bounded to a few hundred / low thousands at most.

Do not create durable DB rows for semantic element references.

Do not persist semantic UI trees to Memory or World State by default.

---

# 9.5 Reuse existing WindowReference

`WindowsDesktopProvider` is the authority for product-owned top-level window refs.

Do not issue a parallel independent `uia-window-*` reference.

The semantic adapter may accept:

`window_ref`

and resolve it through the existing Windows provider.

If the adapter needs PID/HWND internally, obtain it through a product-owned internal method/boundary rather than exposing raw HWND to the model/tool schema.

If a tiny internal helper on `WindowsDesktopProvider` is needed, keep it narrow and non-model-facing.

---

# 9.6 Read-only operations

Implement the minimum semantic read API.

Required:

### 1. `list_windows`

Do not duplicate desktop enumeration if existing `desktop_context()` already provides adequate top-level window snapshots.

Prefer reuse/adaptation.

### 2. `inspect_window(window_ref, depth=...)`

Requirements:

- bounded depth;
- bounded node count;
- bounded text lengths;
- fail closed on stale window ref;
- sensitive-window policy enforced before inspection;
- no unbounded recursive desktop walk.

Recommended defaults:

- default depth <= 3
- hard max depth <= 5
- max elements around 200 unless evidence supports a smaller/better existing project bound

### 3. `find_elements(...)`

Filters may include:

- window_ref required
- control_type optional
- name optional
- automation_id optional

Requirements:

- bounded result count;
- explicit ambiguity;
- no "best guess" silent target choice for future action use.

### 4. `get_element(element_ref)`

Returns a fresh snapshot after re-resolution.

### 5. `get_text_or_value(element_ref)`

Requirements:

- use TextPattern / ValuePattern or normalized provider behavior;
- bounded output length;
- do not expose password/secret controls;
- privacy checks.

### 6. `revalidate_reference(element_ref)`

Must return explicit:

- valid/fresh
- stale/not found
- ambiguous
- sensitive/denied
- unavailable/provider error

Never silently retarget an old ref to a different logical element.

---

# 9.7 Stale target contract

The A1 evaluation demonstrated raw `uiautomation` may surface stale objects through inconsistent low-level COM behavior.

The product-owned adapter MUST normalize this.

Catch only the necessary provider/COM failure families after inspecting actual library exceptions.

Translate into stable JARVIS error codes, e.g.:

- `uia_element_stale`
- `uia_window_stale`
- `uia_element_not_found`
- `uia_element_ambiguous`
- `uia_provider_unavailable`
- `sensitive_window_denied`

Do not leak COM exception strings to the model by default.

Detailed provider error may go to bounded debug/audit metadata if existing policy permits.

---

# 9.8 COM/threading lifecycle

Because UIA/COM can have thread-affinity/initialization behavior:

- inspect how `uiautomation` initializes COM;
- keep provider calls consistent with its supported usage;
- do not scatter COM initialization logic throughout JARVIS;
- centralize any needed initialization inside the adapter;
- no global process hacks unless required;
- tests must cover repeat calls from normal runtime usage.

If async ComputerActionService calls the synchronous UIA provider, use a bounded `asyncio.to_thread` or existing repo pattern only if required and safe.

Do not invent a worker daemon in this milestone.

---

# 9.9 Privacy

Before any semantic tree/text inspection:

- revalidate containing window;
- run existing `PerceptionPrivacyPolicy` checks.

Password/credential fields:

- never return secret value;
- prefer metadata only;
- if provider marks password controls, return redacted/no-value.

Add a regression test.

---

# 9.10 Milestone 1 tests

Create one focused semantic test module, e.g.:

`tests/test_phase_eighteen_semantic_uia.py`

Use a fake/mock provider seam for deterministic CI.

Required unit tests:

- dependency unavailable => truthful unavailable state
- window ref stale => typed stale result
- bounded tree depth
- bounded node count
- find by AutomationId
- find by name + control type
- ambiguous match stays ambiguous
- element ref expires
- element ref re-resolution success
- stale element never silently resolves to different element
- get text/value bounded
- password/sensitive value redacted
- no raw HWND/COM object in returned public snapshot

Windows-only live tests should be separated/skippable when necessary.

Do not make the full suite dependent on a GUI always being present.

---

# 9.11 Milestone 1 real probe

On NIGHTFURY only, if GUI session is available:

Use disposable built-in apps:

- Notepad
- Calculator

Prove read-only:

- list/resolve window
- bounded inspect
- find a known control
- read a safe value/text if available
- close only disposable instances created by this task

Do not touch owner documents.

Do not inspect personal app content.

Record evidence in the batch report.

---

# 9.12 Milestone 1 verification

Run:

```powershell
python -m pytest tests/test_phase_eighteen_semantic_uia.py -q
python -m pytest tests -k "phase_ten or phase_eleven or phase_eighteen" -q
python -m pytest tests -q
python -m compileall src tests -q
git diff --check
```

If dependency has been added to an optional group, also validate project metadata/installability using the repo's established packaging command if one exists.

Do not invent a new packaging workflow if none exists.

Frontend full rerun is optional for this milestone because frontend is untouched, unless repository policy explicitly requires it.

---

# 9.13 Milestone 1 documentation

Update the same batch report.

Minimal canonical updates:

- Current State: semantic provider foundation now implemented/partial
- Gap Register: GAP-0101 remains PARTIAL, not resolved
- Roadmap: A2 semantic foundation milestone completed

Do not mark Computer Use V2 complete.

---

# 9.14 Milestone 1 commit + push

Commit:

`feat: add semantic UIA foundation`

Push same branch.

Record:

`MILESTONE_1_COMMIT`

Then continue.

---

# 10. MILESTONE 2 — WIRE SEMANTIC READ CAPABILITIES THROUGH CANONICAL JARVIS TOOL PATH

## Goal

Make the semantic read foundation actually usable by JARVIS through the existing computer/tool authority.

Still **no semantic actuation** in this milestone.

---

# 10.1 No second service

Integrate behind:

`ComputerActionService`

or the existing canonical computer boundary.

Do not expose the semantic adapter directly from AgentRuntime.

Do not allow ToolRegistry handlers to call raw UIA provider objects directly if that bypasses the ComputerActionService authority.

---

# 10.2 New semantic read actions

Add bounded read-only computer actions consistent with existing naming conventions.

Conceptual operations:

- `semantic_list_windows`
- `semantic_inspect_window`
- `semantic_find_elements`
- `semantic_get_element`
- `semantic_get_text`
- `semantic_revalidate`

Exact naming should follow current action conventions.

Do not create confusing duplicate names if equivalent capabilities already exist.

---

# 10.3 Permission/risk classification

These are observation/read operations.

They may be safe/read-only **only when**:

- sensitive-window privacy policy passes;
- output bounds hold;
- no side effect occurs.

Do not weaken the PermissionEngine globally.

Do not add broad "all computer.* safe" rules.

Define only the necessary action-level permissions using existing policy conventions.

---

# 10.4 Tool Registry

Expose a small bounded semantic-read tool surface.

Do not inject six huge schemas into every prompt if the existing tool-selector can group/select them.

Prefer one coherent tool with action enum if that matches existing `computer.*` architecture and keeps model context smaller.

Or reuse the current computer execute tool if it already multiplexes actions safely.

The goal is:

**minimum model schema, maximum typed backend control.**

Do not expose:

- raw HWND
- coordinates as target IDs
- RuntimeId
- COM selectors
- arbitrary XPath-like UIA traversal language
- arbitrary provider query strings

---

# 10.5 Model-visible output

Outputs must be bounded.

For tree inspection:

- bounded array/tree
- no giant full desktop dump
- no raw untrusted UI text beyond bounded element fields

Remember:

UI text is untrusted data.

It must not become system instruction.

Preserve the already-fixed `verified` model-facing field semantics.

For read-only observations, verification may represent successful fresh observation according to existing result conventions.

Do not label an action as physically verified simply because a provider call returned.

---

# 10.6 Audit

Read operations should follow existing audit conventions.

Do not persist full text of potentially sensitive UI trees when retention policy says not to.

If detailed semantic output is ephemeral, use existing ToolResultRetention mechanisms.

The owner/model can receive current-turn bounded evidence without making it durable automatically.

---

# 10.7 Milestone 2 tests

Required:

- canonical service path used
- PermissionEngine reached
- audit record created according to existing conventions
- sensitive window inspection denied
- stale window rejected
- stale element rejected
- ambiguous element search is not silently collapsed for an action target
- result count bound
- tree size bound
- model/tool output bound
- UI text cannot alter policy/approval behavior
- no filesystem capability introduced

Add at least one end-to-end-ish test:

```text
ToolRegistry/ToolExecutionService
→ ComputerActionService
→ fake SemanticDesktopAdapter
→ bounded result
→ AgentRuntime tool message
```

without real UIA requirement.

---

# 10.8 Milestone 2 real acceptance

On NIGHTFURY:

Use disposable:

- Calculator
- Notepad

Demonstrate through the **actual JARVIS service/tool path**, not by calling `uiautomation` directly:

1. list/find window
2. inspect bounded tree
3. find a control by semantic properties
4. read safe text/value
5. revalidate

No write interaction.

Record in the batch report.

---

# 10.9 Milestone 2 verification

Run focused:

```powershell
python -m pytest tests/test_phase_eighteen_semantic_uia.py -q
```

plus relevant tool/computer tests.

Then:

```powershell
python -m pytest tests -q
python -m compileall src tests -q
git diff --check
```

Frontend optional if untouched.

---

# 10.10 Milestone 2 canonical state update

Minimal only.

Current State should say:

- semantic read tool path implemented on Windows when optional UIA dependency installed;
- no semantic actuation yet at this point.

Gap Register:

- GAP-0101 remains PARTIAL.

Roadmap:

- semantic read integration milestone complete.

---

# 10.11 Milestone 2 commit + push

Commit:

`feat: expose semantic desktop read tools`

Push same branch.

Record:

`MILESTONE_2_COMMIT`

Continue only if green.

---

# 11. MILESTONE 3 — FIRST BOUNDED SEMANTIC UI ACTIONS

## Goal

Add the first safe semantic actuation layer using UIA patterns.

This is intentionally **not** low-level mouse/keyboard automation.

Allowed semantic actions in this milestone:

- `invoke`
- `toggle`
- `select`

Explicitly deferred:

- arbitrary mouse click
- mouse move
- drag
- scroll injection
- arbitrary key press
- arbitrary text typing
- ValuePattern text write / `set_value`
- file-dialog path entry
- raw SendInput expansion
- OCR/vision fallback

---

# 11.1 Why no `set_value` yet

A generic semantic value write could:

- enter arbitrary filesystem paths;
- edit owner content;
- enter credentials;
- bypass the unresolved GAP-0503 boundary in file dialogs.

Therefore do not expose generic ValuePattern mutation in this batch.

Existing bounded text mechanisms remain unchanged.

---

# 11.2 Actuation contract

Every semantic action:

```text
opaque element ref
→ resolve containing window ref
→ privacy check
→ re-resolve semantic element
→ confirm identity
→ confirm required UIA pattern exists
→ permission/risk decision
→ approval when required
→ perform one semantic pattern operation
→ re-observe target/state
→ return truthful verified signal
→ audit
```

No action on a stale or ambiguous reference.

---

# 11.3 Risk/approval policy

Generic semantic actuation can produce consequential effects.

Default these semantic actions to **consequential / approval-required** unless an existing narrower product policy already safely classifies a specific operation.

Do not globally auto-allow InvokePattern.

Examples of dangerous InvokePattern targets include:

- Send
- Delete
- Purchase
- Submit
- Install
- Confirm
- Accept
- security/admin controls

Therefore:

**approval by default** is the safe general contract.

Tests must prove model/UIA cannot bypass approval.

---

# 11.4 Supported patterns

### Invoke

Required pattern:

`InvokePattern`

Behavior:

- target must advertise/support invoke
- otherwise typed `uia_pattern_unsupported`
- revalidate immediately before invoke

Generic invoke result:

- may be `succeeded` with `verified=False` if no generic independent state proof exists;
- never fabricate verified true.

### Toggle

Required pattern:

`TogglePattern`

Verification:

- read state before
- invoke toggle
- read state after
- verified true only if state changed to the expected next state / requested supported target

If API does not accept a desired target state and only toggles, verify change honestly.

### Select

Use the appropriate selection pattern.

Verification:

- re-read selected state after operation;
- verified true only if target reports selected.

---

# 11.5 Target privacy / sensitive controls

Block actuation on:

- password controls;
- privacy-policy denied windows;
- inaccessible/elevated secure desktop;
- stale window;
- stale element;
- ambiguous re-resolution.

Do not attempt UAC/secure-desktop automation.

Return typed failure.

---

# 11.6 File-dialog restriction

If containing window/control context is identified as a standard Open/Save file dialog or known path-entry context:

- do not expose value/text write (already absent);
- do not invoke confirmation actions that would finalize arbitrary path access if the action would bypass the file-access authority.

A generic "Cancel" may be safe but do not add special file-dialog behavior in this milestone unless existing policy already defines it.

Prefer deny/defer over clever bypasses.

---

# 11.7 Verification

Verification is per pattern.

Do not use:

- HTTP-style "call returned" logic
- pattern call success alone
- target disappearance alone as proof of desired outcome

`invoke` often remains unverified generically.

This is acceptable because the model now receives explicit `verified=False`.

Later app-specific adapters can provide stronger verification.

---

# 11.8 Recovery

This milestone needs only bounded immediate recovery:

If revalidation fails before action:

- do not act
- return stale/ambiguous failure

If action provider raises:

- translate to typed provider failure
- no retry loop by default

If verification fails:

- do not repeat action automatically
- return succeeded/unverified or failed according to actual execution evidence and existing result conventions

No blind double-click/retry behavior.

---

# 11.9 Milestone 3 tests

Required:

### Permission / approval

- invoke requires canonical approval
- no actuation before approval
- repeated approval cannot execute twice
- stale pending action cannot execute

### Reference safety

- stale element => no action
- ambiguous re-resolution => no action
- different element with same name => no silent retarget
- expired element => no action

### Pattern safety

- invoke unsupported => typed failure
- toggle supported => correct pattern called
- select supported => correct pattern called
- password/sensitive control => denied

### Verification

- toggle actual state changed => verified true
- toggle call returns but state unchanged => verified false
- selection verified => true
- invoke generic action => never true without evidence

### Architecture

- action travels through ComputerActionService
- PermissionEngine/ApprovalEngine reached
- audit emitted
- no raw provider object exposed
- no shell
- no filesystem action added

---

# 11.10 NIGHTFURY physical/local acceptance

Use only disposable safe apps created by this task.

Recommended:

### Calculator

Use semantic InvokePattern on number/operator controls.

This is safe and reversible.

Example:

- find "Seven"
- request invoke through actual JARVIS action path
- complete required local approval using the normal test/owner path
- verify UI changed using semantic state/text if possible

### Calculator navigation toggle

Use Toggle/Invoke-style safe control if provider exposes it and if it fits the implemented pattern.

### Notepad

Read-only semantic inspection is allowed.

Do **not** modify owner's existing documents.

Do not use set_value.

Do not type text.

### Edge/Chromium

Read-only inspection only for this batch.

No web clicks/navigation through semantic actuation acceptance unless a disposable guest window and a clearly inert control is used; this is optional, not required.

Do not touch owner browser profiles.

---

# 11.11 Milestone 3 full verification

Focused semantic suite.

Relevant computer/permission/approval suites.

Then full:

```powershell
python -m pytest tests -q
python -m compileall src tests -q
git diff --check
```

Frontend full gate should be rerun at final batch completion even if untouched:

```powershell
cd ui
npm test
npm run build
npm audit --audit-level=high
cd ..
```

---

# 11.12 Milestone 3 documentation

Update:

- `02_JARVIS_CURRENT_STATE.md`
- `03_JARVIS_GAP_REGISTER.md`
- `04_JARVIS_EXECUTION_ROADMAP.md`

Only based on actual evidence.

Expected truthful state if fully successful:

### GAP-0101

Can become substantially implemented / potentially resolved only if:

- semantic inspect/search/read
- stale-safe refs
- canonical tool integration
- bounded semantic invoke/toggle/select

are actually green and accepted.

Do not close it merely because classes exist.

### GAP-0102

Remain open:

- rich low-level mouse/keyboard still not implemented.

### GAP-0103

Remain open:

- OCR/local vision fallback not implemented.

### GAP-0104

Likely remain PARTIAL/open:

- broader multi-app recovery still needs later acceptance.

### GAP-0105

Remain open unless this batch builds the full evaluation suite; basic acceptance tests are not the complete eval program.

### GAP-0106

Remain open:

- DPI/multi-monitor/secure-desktop proof still not complete.

### GAP-0503

Remain open.

---

# 11.13 Milestone 3 commit + push

Commit:

`feat: add bounded semantic UI actions`

Push same branch.

Record:

`MILESTONE_3_COMMIT`

Do not merge.

---

# 12. FINAL BATCH REVIEW

After Milestone 3 push, perform one final batch consistency review.

Do not create another large implementation milestone.

Check:

```powershell
git status -sb
git log --oneline --decorate -8
git diff main...HEAD --stat
```

Verify branch history contains clean sequential commits.

Expected new commits from this master task:

1. `fix: close phase 18 checkpoint review`
2. `feat: add semantic UIA foundation`
3. `feat: expose semantic desktop read tools`
4. `feat: add bounded semantic UI actions`

Exact SHAs must be reported.

---

# 13. FINAL FULL REGRESSION GATE

Run once more at the final branch head:

```powershell
python -m pytest tests -q
python -m compileall src tests -q
git diff --check
```

Frontend:

```powershell
cd ui
npm test
npm run build
npm audit --audit-level=high
cd ..
```

Also explicitly confirm:

- no `shell=True` added;
- no `os.system` added;
- no raw COM/UIA object in model-facing output;
- no raw HWND accepted from model input;
- no direct adapter bypass of ComputerActionService;
- no new duplicate authority;
- no silent approval bypass;
- no automatic repeat on uncertain action;
- no filesystem authority expansion;
- no ValuePattern write exposed;
- no arbitrary mouse/keyboard expansion;
- no secret persistence;
- no owner-data acceptance test mutation.

---

# 14. SINGLE BATCH REPORT

Finalize:

`docs/audits/PHASE_18_WORKSTREAM_A_BATCH_01.md`

Sections:

1. starting branch/head
2. Milestone 0
   - review findings
   - brightness fix
   - DEC-046
   - tests
   - commit SHA
3. Milestone 1
   - dependency
   - adapter architecture
   - reference model
   - stale handling
   - privacy
   - live probe
   - tests
   - commit SHA
4. Milestone 2
   - canonical JARVIS integration
   - tool schemas/bounds
   - audit/retention
   - live service-path acceptance
   - tests
   - commit SHA
5. Milestone 3
   - semantic actions
   - risk/approval
   - verification
   - acceptance
   - tests
   - commit SHA
6. final full regression
7. gaps closed/partial/open
8. manual dependencies
9. exact restrictions carried forward
10. recommended next batch

Do not create repetitive per-milestone reports.

---

# 15. MANUAL OWNER ACTION

Expected manual owner action:

`NONE`

This batch should not need:

- API keys
- OAuth
- Home Assistant token
- MQTT credentials
- SSH
- personal data

If a GitHub push authentication issue occurs, report it as a manual gate.

If `computer-uia` installation is required locally for physical probe, normal package installation is allowed because the accepted architecture now includes this optional project dependency. No secret is needed.

---

# 16. STOP CONDITIONS

Stop the entire master task immediately if any milestone encounters:

- unexplained branch/HEAD divergence;
- failing full regression caused by the milestone;
- new P0/P1 security/authority defect;
- second authority would be required;
- raw COM/UIA object must leak across product boundary;
- semantic UIA requires admin/elevation for normal apps;
- dependency fails on supported project Python in a way requiring architecture change;
- stale element cannot be reliably detected;
- actuation cannot be forced through approval;
- filesystem authority would need widening;
- a real secret/API key is required;
- push fails and requires credential intervention.

When stopped:

- keep already-green, already-pushed earlier milestones;
- do not roll them back automatically;
- report which milestone blocked;
- do not partially commit the failed milestone.

---

# 17. GIT DISCIPLINE

For every milestone:

- explicit `git add <paths>`;
- inspect staged diff;
- commit only green milestone;
- push;
- record SHA;
- no amend after push;
- no squash;
- no force push;
- no direct push to main;
- no merge;
- no PR merge;
- no unrelated cleanup.

Documentation changes that belong to a milestone should be committed with that milestone.

---

# 18. FINAL RESPONSE FORMAT

Return one of:

`PHASE18_COMPUTER_USE_BATCH01_PASS`

`PHASE18_COMPUTER_USE_BATCH01_PARTIAL`

`PHASE18_COMPUTER_USE_BATCH01_BLOCKED`

Then:

```text
Branch:
Starting HEAD:
Final HEAD:

Milestone 0:
Commit 0:
Tests 0:

Milestone 1:
Commit 1:
Tests 1:

Milestone 2:
Commit 2:
Tests 2:

Milestone 3:
Commit 3:
Tests 3:

Final Python:
Final Frontend:
Compile/static:
Security review:
Filesystem restriction preserved:
ValuePattern/text-write added:
Mouse/keyboard expansion added:
Manual owner action required:
Open blocking gaps:
Next recommended batch:
Report:
```

Expected values if fully successful:

```text
Filesystem restriction preserved: YES
ValuePattern/text-write added: NO
Mouse/keyboard expansion added: NO
Manual owner action required: NONE
```

Do not merge to main.
