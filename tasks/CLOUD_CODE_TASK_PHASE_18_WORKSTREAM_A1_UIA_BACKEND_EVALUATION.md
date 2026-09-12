# CLOUD CODE TASK — PHASE 18 WORKSTREAM A1
# WINDOWS UIA BACKEND EVALUATION + SEMANTIC FOUNDATION DECISION

**Project:** JARVIS  
**Target agent:** Cloud Code  
**Task mode:** Evidence-driven technical spike / decision gate  
**Owner:** Mahmoud  
**Date:** 2026-09-12  
**Production feature implementation:** NOT YET

---

## 0. Mission

You are starting with **zero prior knowledge** of JARVIS.

Phase 18A.1 audit and Phase 18A.2 stabilization are complete. The current baseline is green and Computer Use V2 may start with explicit restrictions.

Your job in this task is to determine, on the actual NIGHTFURY Windows machine and current JARVIS repository, the best **Windows semantic UI Automation (UIA) backend** for Computer Use V2.

This is not another broad project audit.

This is a narrow engineering spike that resolves the open implementation decision:

> Which backend should JARVIS use for Layer 1 semantic Windows UI Automation?

The locked architecture already says:

1. domain/native API when available;
2. Windows UI Automation (UIA) as the primary general desktop semantic layer;
3. app-specific semantic adapters where useful;
4. visual grounding as fallback;
5. bounded low-level input as later fallback.

Do **not** implement mouse/keyboard automation, visual/OCR fallback, or general Computer Use V2 actions in this task.

Do **not** make a permanent dependency choice without evidence.

---

# 1. Repository bootstrap

Find the real repository root first:

```powershell
git rev-parse --show-toplevel
git status --short
git branch --show-current
git rev-parse HEAD
```

Expected baseline branch:

`main`

The repo-local Source of Truth should now exist.

Do not reset, clean, stash, discard, or overwrite owner changes.

If unrelated tracked modifications make the evaluation unsafe, stop and report them.

---

# 2. Mandatory read order

Read these files before evaluating anything:

1. `AGENTS.md`
2. `docs/source_of_truth/00_JARVIS_START_HERE.md`
3. `docs/source_of_truth/01_JARVIS_CORE_SOURCE_OF_TRUTH.md`
4. `docs/source_of_truth/02_JARVIS_CURRENT_STATE.md`
5. `docs/source_of_truth/03_JARVIS_GAP_REGISTER.md`
6. `docs/source_of_truth/04_JARVIS_EXECUTION_ROADMAP.md`
7. `docs/source_of_truth/05_JARVIS_DECISION_LOG.md`
8. `docs/audits/PHASE_18A1_BASELINE_AUDIT.md`
9. `docs/audits/PHASE_18A2_STABILIZATION.md`

Then inspect the actual current implementation, especially:

- `src/jarvis/computer/`
- `src/jarvis/perception/`
- `src/jarvis/bootstrap.py`
- current Windows-specific utilities
- current dependency declarations
- current tests touching windows/focus/perception/computer control

Current code/tests are implementation truth.

---

# 3. Hard constraints

Preserve all of these:

- NIGHTFURY remains the central authority.
- No second ComputerActionService.
- No second PermissionEngine.
- No second ApprovalEngine.
- No duplicate desktop authority.
- UIA is the general semantic Windows layer.
- Computer actions remain typed, scoped, permissioned, auditable, and verified.
- No coordinate-first architecture.
- No unrestricted shell.
- No arbitrary remote shell.
- No hidden elevation requirement.
- No admin-only design unless strictly unavoidable and explicitly documented.
- No cloud runtime dependency.
- No paid runtime dependency.
- Offline/local operation remains a requirement.
- `winapp` may be evaluated but must not become a hard dependency merely because it is convenient.
- Do not expand filesystem capabilities. F18A1-010/GAP-0503 remains open.
- No new API key or owner secret should be required for this task.

---

# 4. Candidate backends to evaluate

Evaluate the **actual feasible candidates**, not hypothetical marketing descriptions.

At minimum investigate:

### Candidate A — Microsoft `winapp ui`

Evaluate the installed/currently obtainable `winapp` CLI UIA path.

Important current constraint from the project decision log:

- it is a preferred evaluation candidate;
- it is still preview software;
- it must not silently become a mandatory JARVIS runtime dependency.

Assess whether it is best used as:
- primary backend,
- optional accelerator/provider,
- developer/test tool only,
- or rejected for current production use.

### Candidate B — direct Python UIA client

Inspect whether a Python UIA route is practical on the current project/runtime, including relevant libraries such as:

- `uiautomation`
- `pywinauto` UIA backend
- existing `comtypes`/`pywin32` capabilities if already present

Do not permanently install several competing packages into the JARVIS environment just to compare them.

If temporary evaluation requires a package:
- prefer an isolated temporary environment;
- do not modify project dependency files during this spike;
- record exact versions;
- clean up temporary artifacts if safe;
- never fake a test result if installation fails.

### Candidate C — direct native/WinRT/COM integration using existing project capabilities

Only evaluate this as a serious option if the repository already contains enough Windows/native plumbing to make it maintainable.

Do not write hundreds of lines of custom COM glue merely to make this candidate appear viable.

---

# 5. Evaluation criteria

Score each viable candidate against the same criteria.

Use a 1–5 score with evidence.

## 5.1 Required criteria

1. **Semantic coverage**
   - top-level windows
   - control type
   - name
   - AutomationId
   - enabled/offscreen/focusable state
   - bounding rectangle
   - supported patterns/actions
   - text/value retrieval

2. **App coverage**
   - classic Win32
   - modern Windows app / WinUI where available
   - Electron/Chromium accessibility where feasible

3. **Target stability**
   - HWND/process/window identity
   - element identity
   - stale element/reference detection
   - behavior when UI changes between observation and action

4. **Verification support**
   - re-read properties/state after an action in later work
   - ability to re-resolve target before action
   - ability to distinguish target moved/disappeared/stale

5. **Performance**
   - cold start
   - warm inspection
   - element search latency
   - obvious cross-process overhead problems

6. **Runtime footprint**
   - process spawning overhead
   - library size/dependencies
   - memory impact
   - suitability for frequent JARVIS calls

7. **Python compatibility**
   - current project Python
   - supported project minimum Python
   - Windows 11 compatibility

8. **Offline/local behavior**

9. **Licensing/free-runtime suitability**

10. **Stability/maintenance risk**
    - stable library/API versus preview/experimental dependency

11. **Testability**
    - deterministic unit seams
    - realistic integration testing
    - mocking/faking ability

12. **Security/control**
    - no hidden shell interpolation
    - bounded arguments
    - no implicit elevation
    - no broad machine-control bypass

13. **Architecture fit**
    - can sit behind one product-owned JARVIS adapter/interface
    - does not become the authority
    - does not leak vendor-specific concepts throughout AgentRuntime

---

# 6. Real NIGHTFURY probe scenarios

Use safe local apps. Prefer built-in apps so results are reproducible.

At minimum attempt the following where available:

## Scenario 1 — top-level window discovery

Discover:
- Notepad
- Calculator or another built-in Windows app

Record:
- process
- HWND/window identity if available
- title
- bounds
- focus state

## Scenario 2 — semantic tree inspection

For one built-in app:
- inspect a bounded tree;
- record element count/depth;
- identify interactive controls;
- retrieve Name, ControlType, AutomationId where present.

Do not dump an unbounded desktop tree.

## Scenario 3 — semantic search

Find an element using more than one property where possible:
- control type + name
- AutomationId
- parent/window context

Record latency and ambiguity behavior.

## Scenario 4 — read text/value

Open a safe local text app and prove the backend can retrieve a semantic text/value where UIA exposes it.

Do not type anything in this task solely to manufacture success unless the file/app already contains safe disposable text and the operation is fully reversible.

## Scenario 5 — stale reference behavior

Observe an element/window reference.

Then safely cause the target to become invalid using a reversible/manual-safe operation available without affecting owner data (for example open/close a disposable Notepad instance).

Determine:
- how the candidate detects staleness;
- whether it can re-resolve safely;
- whether an old reference might accidentally target a new element.

## Scenario 6 — dynamic UI behavior

Where practical, inspect a UI whose contents change (for example Calculator mode or a disposable dialog) and assess re-query behavior.

No consequential external action.

## Scenario 7 — Chromium/Electron coverage

If a suitable already-installed application is available and accessibility information is exposed, test read-only semantic inspection.

Do not change browser profiles, flags, owner sessions, extensions, cookies, or logins merely to make this test pass.

If Chromium/Electron accessibility is unavailable under current launch conditions, record that truthfully.

---

# 7. Safety of the evaluation

This is primarily **read-only**.

Allowed:
- opening disposable built-in applications;
- listing windows;
- inspecting UIA properties;
- reading UIA values;
- closing only disposable app instances created by this task;
- bounded performance measurements.

Not allowed:
- sending messages/emails;
- altering owner documents;
- file deletion;
- account changes;
- browser login changes;
- system settings changes;
- registry changes;
- installing global automation agents/services;
- elevation/UAC bypass;
- arbitrary mouse/keyboard control;
- modifying JARVIS production Computer Use code.

---

# 8. Dependency discipline

Do not edit `pyproject.toml`, lockfiles, requirements, package manifests, or production bootstrap in this task.

The goal is to select a backend, not silently install it into the product.

If a candidate is already installed, record exact version.

If a candidate is tested temporarily, record:
- exact version;
- how it was isolated;
- whether it required network access;
- whether it required admin rights;
- whether it functioned under the real project Python version.

---

# 9. Decision rules

The recommendation must follow evidence.

## Primary backend requirements

A candidate may be recommended as the **primary JARVIS UIA backend** only if it:

- works locally/offline after installation;
- performs semantic inspection reliably;
- supports re-resolution/stale-target handling;
- can be wrapped behind a product-owned adapter;
- does not require unrestricted shell;
- does not require an online service/API key;
- does not require elevation for normal app inspection;
- has acceptable latency;
- does not force JARVIS to expose vendor-specific concepts to the model.

## Preview dependency rule

If `winapp ui` is the strongest functional tool but remains too volatile to lock as the sole runtime dependency, explicitly consider:

- product-owned adapter interface;
- one stable primary backend;
- `winapp` as optional provider/fallback/developer verifier.

Do not force a binary all-or-nothing decision if a layered provider design is clearly safer.

## No-winner rule

If none of the candidates meets the requirements, return:

`UIA_BACKEND_DECISION_BLOCKED`

Do not implement a weak backend just to finish the task.

---

# 10. Architecture proposal required

Based on the evidence, propose the **smallest** Computer Use V2 semantic contract.

Do not implement it yet.

The proposal should cover only what the next task needs, such as:

### Window reference

A bounded, ephemeral reference containing enough information to re-resolve a window safely, for example:
- session/reference ID
- PID
- HWND where appropriate
- title/class hints
- creation/observation timestamp
- expiry/staleness semantics

### Semantic element reference

Enough information to re-resolve an element without coordinate-first targeting, such as:
- containing window reference
- AutomationId when available
- control type
- name
- bounded ancestry/path hints
- runtime/provider identity only as an implementation detail
- observation timestamp / TTL

### Element snapshot

Machine-readable properties:
- name
- control type
- AutomationId
- enabled
- offscreen
- focused/focusable
- bounds
- supported semantic patterns
- text/value if safe and bounded

### Required operations for the next slice

Recommend the minimum API needed for a future A2 implementation, likely:
- list_windows
- inspect_window
- find_elements
- get_element
- get_text/value
- revalidate_reference

Do not add invoke/click/type in this task.

---

# 11. File/system restriction carry-forward

F18A1-010 / GAP-0503 remains open.

This task must not:
- widen `inspect_file`;
- widen `search_files`;
- widen `open_file`;
- widen `open_folder`;
- add arbitrary path access;
- use UIA work as a backdoor to increase filesystem authority.

Mention this explicitly in the recommendation for the next slice.

---

# 12. Verification

Because this spike must not modify production behavior, preserve the current baseline.

At minimum run:

```powershell
python -m pytest tests -q
python -m compileall src tests -q
git diff --check
```

If no production/UI code is changed, frontend re-run is optional unless repo policy requires it.

Any temporary probe scripts/files must either:
- live outside the repository; or
- be deleted before final status if they are not part of the required report.

Do not leave random benchmark scripts in the repo.

---

# 13. Required report

Create exactly one new persistent artifact for this task:

`docs/audits/PHASE_18_WORKSTREAM_A1_UIA_BACKEND_EVALUATION.md`

Include:

1. starting HEAD/worktree state;
2. current Computer Use implementation summary;
3. candidates actually tested;
4. exact versions;
5. environment/runtime constraints;
6. scenario-by-scenario results;
7. benchmark measurements;
8. 1–5 weighted comparison matrix;
9. reliability/staleness observations;
10. security/authority observations;
11. dependency/maintenance risks;
12. recommended backend topology;
13. proposed minimal semantic contract;
14. explicit carry-forward restrictions;
15. exact next implementation slice;
16. manual owner actions required, if any;
17. final verdict.

Do not update the canonical Decision Log yet unless the owner has already explicitly approved the exact backend choice.

Do not mark the open backend decision as locked merely because this spike recommends one.

---

# 14. Final verdict

Use exactly one:

`UIA_BACKEND_RECOMMENDATION_READY`

`UIA_BACKEND_DECISION_BLOCKED`

Then provide:

```text
Starting HEAD:
Ending HEAD:
Production code changed:
Candidates evaluated:
Recommended primary backend:
Recommended optional/fallback backend:
Why:
Python/runtime compatibility:
Admin/elevation required:
Manual owner action required now:
Filesystem restriction preserved:
May semantic implementation slice A2 start after owner/planner review:
Report:
```

Do not begin A2 implementation in this same task.
