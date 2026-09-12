# CLOUD CODE MASTER TASK — PHASE 18 WORKSTREAM A — BATCH 03
# APPROVAL / FIXTURE HARDENING → FILE-ROOT CONFINEMENT → INPUT + PHYSICAL EVALUATION EXPANSION

**Project:** JARVIS  
**Target agent:** Cloud Code  
**Owner:** Mahmoud  
**Date:** 2026-09-13  
**Branch:** `feature/phase-18-computer-use-v2`  
**Execution model:** one master task, sequential milestones, independent commit + push after every green milestone.

---

# 0. MISSION

You start with **zero prior chat/session context**.

Do not try to reconstruct the project from old phase folders.

This task continues Phase 18 Workstream A after Batch 02.

The owner wants larger Cloud Code sessions, but every large session must still be internally divided into bounded checkpoints.

This batch contains three major milestones:

1. **Milestone 0 — independent-review corrections + fully JARVIS-owned physical UI fixture**
2. **Milestone 1 — close GAP-0503 with a fail-closed approved-root / sensitive-path policy**
3. **Milestone 2 — expand bounded native input + evaluation and physically exercise the owned fixture, including the non-primary monitor**

For each milestone:

```text
READ only what that milestone needs
→ IMPLEMENT
→ FOCUSED TESTS
→ REQUIRED REGRESSION
→ REVIEW DIFF / SECURITY BOUNDARIES
→ UPDATE TRUTHFUL DOCS
→ COMMIT
→ PUSH SAME FEATURE BRANCH
→ CONTINUE ONLY IF GREEN
```

At the very end:

```text
FINAL FULL REGRESSION
→ FINAL REPORT COMPLETION
→ FINAL DOC-ONLY COMMIT
→ PUSH
→ STOP
```

Do not merge to `main`.

Do not force push.

Do not squash.

Do not amend already-pushed commits.

---

# 1. EXPECTED STARTING STATE

Repository:

`MahmoudNagiubX/JARVIS`

Expected local root:

`C:\Jarivs\00_final\jarvis`

Expected branch:

`feature/phase-18-computer-use-v2`

Expected starting HEAD:

`712a9ce033a49602884e2296122300b90acccb1b`

Recent Batch 02 history is expected to include:

```text
712a9ce  docs: finalize phase 18 batch 02 report
0f55417  test: add computer-use evaluation suite
b903de9  feat: add grounded native input fallback
f365d14  fix: harden semantic computer-use targets
2390ddc  feat: add bounded semantic UI actions
```

The independent review confirmed Batch 02 is **four commits ahead of its starting HEAD**, not three, because the final report completion is its own doc-only commit.

This batch intentionally formalizes that pattern:

- 3 implementation milestone commits
- 1 final report/doc-only commit

Before editing:

```powershell
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git status --short
git log --oneline --decorate -12
git remote -v
```

If HEAD differs because an owner-approved commit landed after Batch 02, inspect it before proceeding.

If the divergence is unexplained:

`STOP_UNEXPLAINED_HEAD_DIVERGENCE`

Do not reset/stash/clean owner work.

---

# 2. MINIMAL BOOTSTRAP READ SET

Read:

1. `AGENTS.md`
2. `docs/source_of_truth/01_JARVIS_CORE_SOURCE_OF_TRUTH.md`
3. `docs/source_of_truth/02_JARVIS_CURRENT_STATE.md`
4. `docs/source_of_truth/03_JARVIS_GAP_REGISTER.md`
5. `docs/source_of_truth/04_JARVIS_EXECUTION_ROADMAP.md`
6. `docs/source_of_truth/05_JARVIS_DECISION_LOG.md`
7. `docs/audits/PHASE_18_WORKSTREAM_A_BATCH_02.md`

Then inspect only the relevant implementation:

### Computer authority
- `src/jarvis/computer/service.py`
- `src/jarvis/computer/semantic_uia.py`
- `src/jarvis/computer/native_input.py`
- `src/jarvis/contracts/computer.py`
- `src/jarvis/contracts/semantic_ui.py`
- `src/jarvis/tools/registry.py`
- `src/jarvis/authority/permissions/engine.py`
- `src/jarvis/perception/windows.py`
- `src/jarvis/perception/privacy.py`

### Files
- current `inspect_file`
- current `search_files`
- current `open_file`
- current `open_folder`
- config/bootstrap only as required by the new file policy
- registered-workspace/file policy code only if directly relevant

### Evaluation / scripts
- `src/jarvis/evaluation/service.py`
- `src/jarvis/evaluation/computer_use_v2.py`
- `src/jarvis/evaluation/semantic_uia_fixtures.py`
- `scripts/phase18/computer_use_acceptance.py`

### Tests
- Phase 18 semantic/native/evaluation tests
- existing file/computer tests discovered by references

Do not read the giant historical Master by default.

---

# 3. LOCKED ARCHITECTURE

Preserve:

```text
AgentRuntime
→ ToolExecutionService
→ PermissionEngine
→ ApprovalEngine when required
→ ComputerActionService
→ WindowsNativeComputerController
→ semantic UIA / native-input / bounded file policy
→ OS
→ independent observation / verification
→ result + audit + event
```

Exactly one logical authority each.

Do not create:

- `ComputerActionServiceV2`
- another PermissionEngine
- another ApprovalEngine
- a second audit service
- raw model → UIA
- raw model → SendInput
- raw model → filesystem
- arbitrary shell
- arbitrary PowerShell
- raw coordinate tool
- raw HWND tool
- raw VK/scancode tool

UIA remains the primary semantic target identity.

Native input is a **fallback execution mechanism**, never a replacement for grounding.

---

# 4. CRITICAL PHYSICAL-TEST SAFETY RULE

Batch 02 had one real physical-test incident:

A supposed disposable Notepad probe attached to the owner's live Windows 11 Notepad single-instance session and likely caused loss of one unsaved tab.

The owner reported no material harm, but this is still a real testing-process failure.

Therefore, from this batch forward:

## NEVER use an owner-installed general application as the main acceptance fixture merely because you launched its EXE.

Do not use these as disposable fixture hosts:

- Notepad
- normal Edge/Chrome
- VS Code
- terminal
- Explorer
- email/chat apps
- Settings
- owner document apps

unless the task explicitly proves an isolated profile/process and exact cleanup ownership.

## No generic image-name cleanup

Physical acceptance code must NOT use broad cleanup like:

```text
taskkill /IM msedge.exe
taskkill /IM notepad.exe
taskkill /IM python.exe
```

for a fixture.

Cleanup must own the **exact child process** it launched.

Prefer:

```text
Popen PID
→ exact child-process termination
→ exact process wait
```

No unrelated owner process may be killed.

## No Edge Guest fixture in Batch 03

Even Guest mode is hosted by Edge's multi-process/shared browser architecture and is not worth retaining as the primary physical fixture after the incident.

Batch 03 replaces it with a fully JARVIS-owned native Win32 fixture process.

---

# 5. EXTERNAL TECHNICAL BASIS FOR THE OWNED FIXTURE

Microsoft's current UI Automation documentation explicitly lists standard Win32 controls as UIA-supported, including:

- `Button`
- `CheckBox`
- `ComboBox`
- `ListBox`
- `ListItem`
- standard text/edit controls

This makes a small Win32 fixture a substantially better acceptance surface than browser DOM content hidden below Chromium's deeper accessibility tree.

Do not change the production UIA depth bound merely to make Edge pass.

Use a product-owned fixture first.

---

# 6. INDEPENDENT REVIEW FINDINGS AGAINST BATCH 02

The actual GitHub commits were reviewed after Batch 02.

Core semantic/native code is acceptable as a base.

The following hardening issues are newly identified.

---

## R18B02-001 — target-aware approval is limited to semantic pattern actions

Current `ComputerActionService` has:

`_semantic_actuation_actions`

containing only:

- semantic_invoke
- semantic_toggle
- semantic_select

Those actions receive:

- trusted target preview
- target identity digest
- short target-bound approval
- revalidation on resume

But:

`computer.pointer.act`

also acts on an `element_ref`.

Current pointer approval goes through generic `_approval_preview(action)`.

That means the owner can be asked to approve something like:

```text
pointer_left_click
element-<uuid>
```

without the same human-readable target binding.

It also receives the generic long approval window.

### Required correction

Generalize the concept from:

`semantic_actuation_actions`

to:

`element_targeted_actions`

or equivalent.

At minimum include:

- semantic_invoke
- semantic_toggle
- semantic_select
- pointer_move_to_element
- pointer_left_click_element
- every new element-targeted pointer action added later in this batch

All element-targeted actions must receive:

- fresh trusted element preview
- actionable/strong identity requirement
- identity digest binding
- target-lifetime-bounded approval
- re-check on decide

The target preview may include only safe metadata:

- action
- bounded element name
- control type
- AutomationId
- window/app label if safely available
- opaque element ref
- approval expiration

Never text/value content.

---

## R18B02-002 — semantic approval TTL uses the default constant, not the actual reference deadline

Current code limits semantic approval with:

`now + ELEMENT_REF_TTL_SECONDS`

where the constant is currently 45 seconds.

But `WindowsUIAutomationAdapter` supports configurable element TTL clamped to 15–60 seconds.

The approval requirement is:

> approval must not outlive the actual target reference.

Using the default constant is only correct for the default adapter configuration.

### Required correction

Do not infer reference validity from a global constant.

Expose a bounded, product-owned internal target descriptor/preview that includes:

`reference_expires_at`

or:

`reference_valid_for_ms`

derived from the actual `_ElementRefEntry`.

Do not expose raw provider identity.

Do not expose RuntimeId/digest.

The approval deadline must be:

```text
min(generic approval deadline, actual target reference expiry)
```

The trusted preview/descriptor call itself may refresh the target only according to an explicitly documented rule.

Do not accidentally extend a reference lifetime forever every time the approval screen polls.

Preferred behavior:

- one approval-preparation revalidation may refresh once;
- the pending approval stores the concrete expiry it received;
- repeated UI polling of the approval preview must not keep extending it.

Add regression tests with non-default 15-second TTL.

---

## R18B02-003 — window-targeted native-key approval is still opaque / weakly bound

`computer.keyboard.key` targets a `window_ref`.

The generic approval preview exposes parameters, but not a trusted, human-understandable window identity.

A window ref is opaque.

### Required correction

For window-targeted input actions:

- `keyboard_key`
- existing bounded literal keyboard type when it requests approval
- any future window-grounded hotkey action

build a trusted window-target preview from the existing `WindowsDesktopProvider`.

Preview:

- action
- bounded safe window title
- process name
- opaque window ref
- key/action name
- text length/digest only for literal typing (never raw text in approval durable data)

Bind pending approval to the existing stable window fingerprint:

- window ref
- PID
- class/process/title fingerprint using existing product-owned window-reference semantics

Do not expose PID/HWND to the model-facing tool.

On approval resume:

- revalidate window ref;
- if changed/stale/sensitive → refuse before injection.

Approval expiry must not exceed the current window-ref lifetime if that can be obtained safely.

If exact window expiry is not currently exposed internally, add a narrow product-owned internal descriptor analogous to the element-target descriptor.

Do not create another window-ref store.

---

## R18B02-004 — shared-application physical fixture is too risky

The Batch 02 runner's Edge fixture uses:

```text
msedge.exe --guest --new-window ...
```

and cleans up via the launched PID's process tree.

This is better than broad image-name cleanup, but Edge is still a multi-process browser with shared installation/runtime behavior.

It also failed to reach the page at the current bounded UIA depth.

There is no reason to keep it as the principal physical fixture.

### Required correction

Replace the Edge Guest fixture with a dedicated JARVIS-owned process:

`scripts/phase18/uia_fixture_host.py`

or a comparably named tool.

Requirements:

- own Python process
- native Win32 window through `ctypes` / standard controls
- unique title nonce supplied at launch
- no network
- no file chooser
- no owner profile
- no persistent data
- exact PID owned by runner
- runner waits for exact child exit
- runner kills only this child if necessary
- temp artifacts cleaned
- never searches/acts on another window unless title nonce matches exactly
- collision => abort

Recommended standard controls:

1. Push Button — should expose Button / Invoke
2. Auto CheckBox — should expose CheckBox / Toggle
3. ListBox with two or three items — ListItem / SelectionItem target
4. Static status text — independent read-back
5. optional two buttons/controls for focus/key testing

The host should update safe status labels/messages when:

- button invoked
- checkbox state changes
- list selection changes
- click/right-click/double-click/scroll test event happens if later needed

Do not require internet or browser accessibility.

---

## R18B02-005 — acceptance runner must never attach to pre-existing fixtures

Every physical fixture must have an unpredictable per-run nonce.

Example title:

`JARVIS-CUV2-FIXTURE-<uuid>`

Runner must:

- generate nonce;
- pass nonce to child;
- wait only for exact title;
- optionally verify exact child PID internally where safely available;
- fail if multiple matches;
- never fall back to "first window with similar title".

No bare `"Calculator"` / `"Notepad"` / generic title matching as the primary Batch 03 fixture.

---

## R18B02-006 — finalization commit is a real commit and must be planned

Batch 02's implementation had 3 milestones but final HEAD contained a fourth doc-only commit.

That is fine, but reports/prompts must not claim "exactly three new commits".

Batch 03 explicitly expects:

1. Milestone 0 commit
2. Milestone 1 commit
3. Milestone 2 commit
4. final report commit

---

# 7. MILESTONE 0 — APPROVAL HARDENING + OWNED WIN32 UIA FIXTURE

## Goal

Close R18B02-001 through R18B02-006 and obtain physical semantic evidence from an owned fixture.

This milestone must not yet implement filesystem confinement or new input gestures.

---

# 7.1 Generalize trusted target descriptors

Do not keep target-awareness embedded as a special semantic-action exception.

Create a narrow product-owned internal mechanism.

Possible conceptual shapes:

```text
ElementTargetDescriptor
WindowTargetDescriptor
```

They are not model tools.

They may contain internal fields required for approval binding, but raw HWND/COM/RuntimeId must still stay inside provider boundaries.

### Element descriptor

Safe/public-ish preview data:

- element_ref
- window_ref
- bounded name
- control_type
- automation_id
- actionable
- expires_at

Internal binding:

- stable opaque identity digest generated by the product
- no raw RuntimeId

### Window descriptor

Safe preview:

- window_ref
- title bounded
- process name bounded
- expires_at if available

Internal binding:

- existing window fingerprint digest / stable internal identity

Reuse `WindowsDesktopProvider`.

No second reference store.

---

# 7.2 Approval preparation

Before creating approval for any element-targeted action:

```text
trusted descriptor
→ strong/actionable target
→ safe preview
→ exact expiry
→ identity digest
→ pending record
```

Before window-targeted input:

```text
trusted window descriptor
→ privacy pass
→ fresh window ref
→ safe preview
→ identity binding
→ pending record
```

Never derive approval target identity from model-provided title/name.

---

# 7.3 Approval resume

On `decide()`:

- consume durable approval as currently designed;
- before execution, re-fetch trusted target descriptor;
- compare binding digest;
- if changed → `approval_target_changed`
- if stale → typed stale error
- if privacy now denies → typed denial
- if ref expired → no action
- no auto-reminting approval
- no auto-retry

Existing repeated-decide protection remains.

---

# 7.4 Human-readable preview

Approval previews should be understandable without exposing sensitive payload.

### Element-target action

Conceptual shape:

```json
{
  "action": "pointer_left_click_element",
  "target": {
    "name": "Invoke Target",
    "control_type": "ButtonControl",
    "automation_id": "..."
  },
  "element_ref": "element-...",
  "expires_at": "..."
}
```

Follow existing project serialization conventions.

### Window key action

Conceptual shape:

```json
{
  "action": "keyboard_key",
  "key": "tab",
  "window_title": "JARVIS-CUV2-FIXTURE-...",
  "process_name": "python.exe",
  "window_ref": "window-...",
  "expires_at": "..."
}
```

### Literal typing

Never store raw typed text in durable approval preview.

Keep:

- text length
- digest
- trusted window label

Existing ephemeral argument behavior remains.

---

# 7.5 Owned native Win32 fixture host

Create:

`scripts/phase18/uia_fixture_host.py`

or equivalent.

It is evaluation-only.

It must never be imported into production startup.

Implement with stdlib/ctypes if practical.

No new GUI framework dependency solely for the fixture.

Use native controls documented by Microsoft UI Automation support.

Recommended layout:

```text
Top-level Win32 window
  Static: "JARVIS fixture ready"
  Push button: "Invoke Target"
  Auto checkbox: "Toggle Target"
  ListBox:
     Alpha
     Beta
     Gamma
  Static status:
     status=idle
  Optional second focusable button
```

Actions should update the status label so the acceptance runner has independent read-back.

For example:

- push button → status `invoked`
- checkbox → status `toggle:on/off`
- selection → status `selected:Beta`

The runner must not need direct IPC to claim success.

It should verify via JARVIS semantic read of the status UI.

---

# 7.6 Fixture lifecycle

Runner:

1. generate random nonce
2. launch exact host script as child process
3. child title includes nonce
4. child writes/prints a single readiness marker if useful
5. runner uses `computer.semantic.read list_windows`
6. select exact nonce title only
7. require exactly one match
8. run tests
9. request child shutdown safely if a control is provided
10. otherwise terminate exact Popen child only
11. `wait()`
12. verify exact child is gone

No image-name kill.

No browser.

No Notepad.

No Calculator required for Milestone 0.

---

# 7.7 Required physical semantic acceptance

Through actual JARVIS tools only:

### Invoke

- find exact push button
- confirm actionable/strong
- `computer.semantic.act invoke`
- approval preview human-readable
- approve
- independent status read → `invoked`

### Toggle

- find exact checkbox
- verify `Toggle` pattern
- request toggle
- approve
- independent state/status read

### Select

Prefer a ListItem exposing SelectionItemPattern:

- find `Beta`
- request select
- approve
- independent selected/state/status read

If the standard Win32 fixture unexpectedly does not expose the expected pattern:

- record exact patterns observed
- do not force production behavior
- investigate fixture style/version first
- do not expand global tree depth as a drive-by workaround

Run semantic fixture acceptance:

`3 clean iterations`

No retry-until-green.

Record all 3.

---

# 7.8 Milestone 0 tests

Add/modify tests for:

- element-target pointer action receives trusted preview
- pointer approval is identity-bound
- pointer approval target change refuses execution
- actual element TTL 15 sec bounds approval <= 15 sec
- polling/preview does not indefinitely extend pending approval
- window key approval includes trusted window title/process
- key approval stale window refuses
- literal typing preview has trusted window + text length/digest, not raw text
- owned fixture runner rejects title collisions
- owned fixture kills exact PID only
- acceptance runner contains no broad `taskkill /IM`
- runner contains no `msedge`/Notepad dependency
- fixture is not imported by production

Regression:

```powershell
python -m pytest tests -k "phase_eighteen" -q
python -m pytest tests -q
python -m compileall src tests scripts -q
git diff --check
```

---

# 7.9 Milestone 0 report

Create:

`docs/audits/PHASE_18_WORKSTREAM_A_BATCH_03.md`

This is the only Batch 03 audit report.

Record:

- review findings
- fixes
- fixture design
- 3-run physical evidence
- incident-safety improvements

Do not claim GAP-0101 resolved until actual results support it.

---

# 7.10 Milestone 0 commit

Commit:

`fix: harden computer target approvals and fixtures`

Explicit stage only.

Push.

Record SHA.

Continue only if green.

---

# 8. MILESTONE 1 — GAP-0503 FILE-ROOT CONFINEMENT

## Goal

Close the long-standing unrestricted file-access gap.

Current code allows caller-supplied absolute paths for:

- `inspect_file`
- `search_files`
- `open_file`
- `open_folder`

without approved-root confinement or a meaningful sensitive-path deny policy.

This must be fixed before any future file-dialog automation.

---

# 8.1 One product-owned file access policy

Implement one bounded policy, conceptually:

`FileAccessPolicy`

Preferred module:

`src/jarvis/computer/file_access.py`

or a repo-consistent location.

Do not create another permission engine.

This policy answers:

```text
is this concrete path within an owner-approved root
AND not a sensitive path
AND not an escape/reparse traversal?
```

It is subordinate to PermissionEngine.

---

# 8.2 Approved roots are explicit

Do not silently approve:

- entire C:\
- user's entire home directory
- AppData
- ProgramData
- Windows
- arbitrary current working directory

Approved roots must come from explicit local configuration.

Follow existing `JarvisConfig` environment/config conventions.

Preferred conceptual config:

`file_access_roots: tuple[str, ...]`

Environment form may be:

`JARVIS_FILE_ACCESS_ROOTS`

using the platform path separator.

Do not invent a second config subsystem.

### Fail-closed default

If no root is configured:

file operations that require a path must return a typed denial, e.g.:

`file_root_not_configured`

This is an intentional security tightening.

Do not preserve insecure "any path" behavior merely for backwards compatibility.

### No manual owner action required for this batch

Tests and physical acceptance can create a temporary root and inject/configure it.

The owner can configure personal roots later when actual file workflows are started.

Document this truthfully.

---

# 8.3 Root model

Requirements:

- bounded count of configured roots
- normalize each once at startup/policy construction
- absolute paths only after normalization
- root itself must not be a sensitive system root
- deduplicate equivalent roots
- Windows case-insensitive comparisons handled correctly
- prefix confusion must not work:
  - allowed `C:\Data`
  - must NOT allow `C:\Database`

Use proper path containment, not string prefix matching.

---

# 8.4 Sensitive path policy

Sensitive paths must be denied even when nested under an approved broad root.

At minimum consider component-aware protections for:

### Credential/key stores

- `.ssh`
- `.gnupg`
- `.aws`
- `.azure`
- `.kube`
- private key filenames/extensions
- credential/token files

### Environment secrets

Deny actual local secret env files such as:

- `.env`
- `.env.local`
- `.env.production`

Do not unnecessarily deny a deliberately safe template such as:

`.env.example`

unless repo policy says otherwise.

### Browser secret databases

Recognizable sensitive profile files such as:

- `Login Data`
- `Cookies`
- `Web Data`

### OS credential/security stores

Deny obvious Windows credential/SAM/security-sensitive locations.

Approved-root confinement remains the primary boundary.

Sensitive deny rules are defense in depth.

---

# 8.5 Path resolution / escape resistance

For every file/folder path:

1. parse
2. resolve/canonicalize
3. confirm contained in approved canonical root
4. reject sensitive path
5. execute only then

### Symlinks / junctions / reparse points

A path physically resolving outside an approved root must be denied.

Search traversal must not follow links/junctions out of root.

Do not trust lexical containment alone.

Use the strongest stdlib checks available on supported Python/Windows versions.

If junction detection is platform/version-specific, isolate it and test conditionally.

---

# 8.6 Search behavior

Replace unsafe broad `Path.rglob()` behavior if necessary.

Search requirements:

- root itself approved
- bounded result count
- bounded traversal
- no link/junction escape
- every returned file individually rechecked
- sensitive children omitted
- no secret path names leaked when policy blocks them

Deterministic behavior:

- requested root denied → typed denial
- sensitive child subtree → skip + optional filtered count
- do not reveal exact hidden sensitive path names in model-visible output

---

# 8.7 Inspect behavior

`inspect_file`:

- file inside approved root
- deny sensitive
- preserve existing file-size bound
- preserve bounded decoding
- no binary dump
- no credential exception

---

# 8.8 Open file / folder

`open_file` / `open_folder`:

- must pass same root policy
- still go through ComputerActionService
- no direct shell
- no file picker
- no alternate path

Do not weaken existing risk/approval semantics.

---

# 8.9 Tool schemas

Do not add "bypass", "allow_external", or "unsafe" flags.

Return typed codes, e.g.:

- `file_root_not_configured`
- `file_path_outside_allowed_root`
- `file_sensitive_path_denied`
- `file_path_escape_denied`

Exact names may follow project conventions.

---

# 8.10 Configuration visibility

Expose only bounded status if useful:

- configured/unconfigured
- root count

Do NOT expose personal root strings to the model unless actually required.

Do not write configured roots to Memory.

---

# 8.11 File policy tests

Required:

### root confinement

- file inside allowed root → allowed
- folder inside → allowed
- sibling prefix `Data2` → denied
- `..` traversal → denied after resolve
- absolute outside → denied
- no roots → denied
- duplicate root normalization

### link/reparse

- symlink inside root → target outside root → denied
- search does not follow escape link
- junction test on Windows if supported

### sensitive

- `.ssh/id_rsa` denied
- `.env` denied
- `.env.example` behavior explicitly tested
- browser Login Data denied
- normal source `.py` / `.txt` allowed

### integration

- inspect_file uses policy
- search_files uses policy
- open_file uses policy
- open_folder uses policy
- no alternate direct path bypass
- canonical audit remains

---

# 8.12 Physical/local file acceptance

Use `tempfile.TemporaryDirectory()` as one explicit approved root.

Create:

```text
allowed/
  normal.txt
  sub/
    note.txt
  .env
outside/
  outside.txt
```

Where practical create a link inside allowed that points outside.

Through actual JARVIS tool/service path:

- inspect normal.txt → success
- search normal → success
- inspect `.env` → denied
- inspect outside → denied
- link escape → denied

Do not use owner files.

Clean all temp data.

---

# 8.13 GAP-0503 closure criteria

Only mark GAP-0503 `RESOLVED` if:

- all four current path capabilities are behind the policy
- no known direct bypass exists
- symlink/reparse escape is addressed
- sensitive path policy exists
- fail-closed default exists
- tests + actual service-path temp-root acceptance pass

File dialogs remain unimplemented after closure.

Closing GAP-0503 means underlying path authority is safe enough for later work.

---

# 8.14 Milestone 1 verification

```powershell
python -m pytest tests -k "computer or file or phase_eighteen" -q
python -m pytest tests -q
python -m compileall src tests scripts -q
git diff --check
```

---

# 8.15 Milestone 1 commit

Commit:

`fix: confine computer file access to approved roots`

Push.

Record SHA.

Continue only if green.

---

# 9. MILESTONE 2 — INPUT EXPANSION + OWNED-FIXTURE EVALUATION + MULTI-MONITOR PHYSICAL PROOF

## Goal

Advance GAP-0102 and GAP-0105 using the new owned fixture.

Do not add drag/drop or paste yet.

---

# 9.1 Extend pointer actions

Add only:

- `right_click_element`
- `double_click_element`
- `scroll_element`

Existing:

- move_to_element
- left_click_element

remains.

Still no raw coordinates.

All actions accept an `element_ref`.

---

# 9.2 Right click

Pipeline:

```text
trusted element target
→ approval with element preview
→ fresh grounding
→ focus/foreground check
→ fresh grounding again
→ move pointer
→ RIGHTDOWN + RIGHTUP
→ bounded post observation
→ generic verified false unless independent fixture evidence
```

Do not assume context menu opened merely because input was delivered.

---

# 9.3 Double click

Use a bounded Windows double-click input sequence.

Do not expose timing to the model.

Use system double-click timing if needed from `GetDoubleClickTime()`.

Do not allow arbitrary click count.

Exact action:

`double_click_element`

only.

Generic result remains unverified without app postcondition.

---

# 9.4 Scroll

`scroll_element`

Parameters:

- element_ref
- direction: `up | down`
- steps: integer 1..5

No raw wheel delta from model.

Internally:

`WHEEL_DELTA = 120`

Use bounded signed multiple.

Before scroll:

- target actionable
- foreground correct
- pointer grounded over target

After scroll:

- no generic "content changed" claim
- report delivery evidence only

---

# 9.5 Named chord surface

Add a very small explicit chord allowlist, not arbitrary hotkeys.

Preferred initial set:

- `ctrl+a`
- `ctrl+c`
- `ctrl+f`
- `ctrl+z`
- `ctrl+y`

Do not add:

- ctrl+v / paste
- ctrl+s
- alt+f4
- Windows-key combinations
- Ctrl+Alt+Delete
- arbitrary free-form modifier + key parser

Tool may be:

`computer.keyboard.chord`

with enum.

All chords are approval-required and window-target-aware.

The trusted approval preview must show exact chord + trusted target window.

No raw VK.

---

# 9.6 No paste yet

Clipboard paste is explicitly deferred.

Reason:

- clipboard may contain secrets
- current contents may be unknown to the owner
- durable approval preview must not expose raw clipboard contents

Do not add Ctrl+V.

---

# 9.7 No drag/drop yet

Drag/drop remains deferred because:

- multi-target semantics
- possible filesystem/object transfer
- harder verification
- future workflows should build on Milestone 1's safe file policy

---

# 9.8 Expand owned fixture for input verification

The fixture may add safe event observation for:

- right click
- double click
- scroll
- focus/chord behavior

Status text records only known-safe fixture event names.

No owner data.

No network.

---

# 9.9 Physical semantic acceptance — close GAP-0101 if evidence passes

Using the owned fixture, run 3 times:

- InvokePattern
- TogglePattern
- SelectionItemPattern

Independent status/state read-back each time.

If all 3 pass reliably 3/3:

GAP-0101 may be marked `RESOLVED` for the semantic capability defined by that gap.

This does not mean all Computer Use is complete.

If expected UIA pattern is absent:

record actual patterns and keep PARTIAL.

Do not mutate production semantics just to satisfy the fixture.

---

# 9.10 Physical pointer acceptance

Attempt 3 runs each for:

- left click
- right click
- double click
- scroll

Use independent fixture status/state where possible.

Generic action result remains honest.

No retry-until-green.

---

# 9.11 Non-primary monitor proof

NIGHTFURY previously reported:

```text
X origin = -1920
Y origin = 0
width = 3840
height = 1080
monitors = 2
```

The owned fixture process may safely position **its own window**.

Add an evaluation-only option such as:

`--x -1500 --y 100`

or equivalent.

Do not add a general production arbitrary-window coordinate move capability.

Runner:

1. confirm actual topology still supports negative-X
2. launch fixture on negative-X monitor
3. find exact nonce title
4. confirm UIA bounds are on non-primary monitor
5. run grounded pointer left click
6. independently verify fixture status
7. clean exact fixture child

If topology differs:

mark physical multi-monitor pending; do not fail code.

If successful:

record `NON_PRIMARY_MONITOR_PHYSICAL_PASS`.

---

# 9.12 DPI

Current physical evidence is 96 DPI / 100%.

Do not alter Windows scaling.

Do not fake non-100% DPI.

Keep non-100% physical DPI proof pending unless hardware/config already offers it.

---

# 9.13 Evaluation suite expansion

Extend existing:

`computer_use_v2`

suite.

Do not create another evaluation authority.

Add meaningful cases for:

- pointer target-aware approval
- actual ref expiry bounds approval
- trusted window-target approval
- file-root confinement
- sensitive-path denial
- symlink/junction escape refusal
- right-click/double-click/scroll stay element-grounded
- chord allowlist rejects raw combinations
- no Ctrl+V
- no drag/drop
- exact-PID fixture ownership
- nonce collision refusal
- no external owner app required
- non-primary-monitor fixture geometry

Do not mechanically duplicate unit tests.

---

# 9.14 Physical runner output

Update:

`scripts/phase18/computer_use_acceptance.py`

to use only the owned fixture for the expanded scenarios.

Summary may contain only:

- scenario names
- pass/attempt counts
- bounded latency
- verification booleans/reasons
- monitor geometry metadata

No full window lists.

No owner titles.

No arbitrary raw UI contents.

---

# 9.15 3-run physical gate

Run 3 clean iterations.

Report:

- semantic invoke
- semantic toggle
- semantic select
- left click
- right click
- double click
- scroll
- Tab/key
- at least one harmless allowed chord if fixture supports proof
- non-primary-monitor left click

No hidden retries.

---

# 9.16 Milestone 2 verification

Focused:

```powershell
python -m pytest tests -k "evaluation or phase_eighteen" -q
```

Full:

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

---

# 9.17 Gap status rules

### GAP-0101

Resolve only with strong code + owned-fixture physical evidence for invoke/toggle/select.

### GAP-0102

Remain `PARTIAL` even if this milestone passes because paste/drag-drop/arbitrary hotkeys remain absent.

### GAP-0104

May remain `PARTIAL`.

### GAP-0105

May advance substantially but do not claim the broad real-app matrix is complete if only the owned fixture is covered.

### GAP-0106

If non-primary monitor physical input passes, record that subproblem as physically proven.

Keep non-100%-DPI / secure-desktop physical proof pending.

### GAP-0503

Should be `RESOLVED` if Milestone 1 closure criteria passed.

---

# 9.18 Milestone 2 commit

Commit:

`feat: expand grounded input and computer-use evaluation`

Push.

Record SHA.

---

# 10. FINAL FULL REVIEW

After all three milestones:

```powershell
git status -sb
git log --oneline --decorate -15
git diff 712a9ce033a49602884e2296122300b90acccb1b...HEAD --stat
```

Confirm implementation commits:

1. `fix: harden computer target approvals and fixtures`
2. `fix: confine computer file access to approved roots`
3. `feat: expand grounded input and computer-use evaluation`

Then run final full regression again.

---

# 11. FINAL SECURITY CHECKLIST

Explicitly confirm:

## Authority

- one ComputerActionService
- one PermissionEngine
- one ApprovalEngine
- no direct tool→adapter bypass

## UI targeting

- no weak identity action
- no stale action
- pointer approval target-bound
- window key approval target-bound
- approval cannot outlive actual ref
- no polling TTL extension bug

## Native input

- no raw x/y model inputs
- no raw HWND
- no raw VK/scancode
- no arbitrary hotkey string
- no Ctrl+V
- no drag/drop
- no UIAccess/elevation
- partial SendInput truthful failure

## Files

- no default unrestricted disk access
- no string-prefix root comparison
- link/junction escape addressed
- sensitive-path deny exists
- no file dialog automation
- no path policy bypass

## Physical test safety

- no Notepad
- no Edge/Chrome dependency
- no broad process-name kill
- exact fixture PID cleanup
- unique nonce title
- collision refuses
- no owner windows acted on
- no owner documents touched
- no secrets logged

---

# 12. FINAL REPORT COMPLETION

Finalize:

`docs/audits/PHASE_18_WORKSTREAM_A_BATCH_03.md`

Required sections:

1. start state
2. independent review findings
3. Milestone 0
4. Milestone 1
5. Milestone 2
6. physical results table
7. final tests
8. security review
9. gap state
10. manual dependencies
11. incident-safety changes
12. recommended next batch

Record exact implementation commit SHAs.

---

# 13. FINAL DOC-ONLY COMMIT

After implementation commits are pushed and final regression is complete:

Commit only final report/state fill-ins if needed.

Message:

`docs: finalize phase 18 batch 03 report`

Push.

This commit is expected.

Do not claim the batch created only three commits.

Expected total Batch 03 commits:

`4`

unless no post-push report fill-in exists.

No amend.

---

# 14. MANUAL OWNER ACTION

Expected:

`NONE`

For file access:

default policy may be unconfigured/fail-closed after this batch.

That is acceptable.

Do not ask the owner to choose personal roots during implementation.

Physical file policy acceptance uses temporary roots only.

For non-primary monitor testing:

the owned fixture may position its own window.

No owner assistance should be needed if the reported 2-monitor topology remains present.

---

# 15. STOP CONDITIONS

Stop current/later work if:

- unexpected HEAD divergence
- wrong-target physical action
- fixture attaches to non-owned window
- any owner process is terminated
- element approval can outlive actual target
- target binding bypass exists
- file path escape remains possible
- symlink/junction escape cannot fail closed
- approved roots require silently approving entire home/C:
- raw coordinate/VK interface becomes necessary
- native input requires elevation/UIAccess
- production must depend on evaluation fixture
- full tests regress
- new P0/P1 security problem appears
- push auth fails

Keep already-pushed green milestones.

Never partially commit a blocked milestone.

---

# 16. GIT DISCIPLINE

Per milestone:

```text
git status --short
git diff
focused tests
full required gate
git diff --check
git add EXPLICIT_PATHS_ONLY
git diff --cached
git commit
git push origin feature/phase-18-computer-use-v2
```

Never:

`git add .`

No merge.

No force.

No direct main push.

---

# 17. FINAL RESPONSE FORMAT

Return one verdict:

`PHASE18_COMPUTER_USE_BATCH03_PASS`

`PHASE18_COMPUTER_USE_BATCH03_PARTIAL`

`PHASE18_COMPUTER_USE_BATCH03_BLOCKED`

Then:

```text
Branch:
Starting HEAD:
Final HEAD:

Independent review findings closed:

Milestone 0:
Commit 0:
Tests 0:
Owned fixture:
Semantic invoke physical:
Semantic toggle physical:
Semantic select physical:

Milestone 1:
Commit 1:
Tests 1:
File policy:
No-root behavior:
Sensitive path:
Escape/link tests:
Service-path physical temp-root acceptance:
GAP-0503:

Milestone 2:
Commit 2:
Tests 2:
Right click:
Double click:
Scroll:
Chord:
3-run physical suite:
Non-primary monitor:
DPI:
Evaluation suite:

Final report commit:
Commit 3:

Final Python:
Final Frontend:
Compile/static:
Security review:

GAP-0101:
GAP-0102:
GAP-0104:
GAP-0105:
GAP-0106:
GAP-0503:

Owner app touched:
Broad process kill used:
Raw coordinate model input:
Raw VK model input:
Arbitrary hotkey input:
Paste added:
Drag/drop added:
File dialog automation added:
ValuePattern write added:
Manual owner action required:

Next recommended batch:
Report:
```

Expected safety outputs:

```text
Owner app touched: NO
Broad process kill used: NO
Raw coordinate model input: NO
Raw VK model input: NO
Arbitrary hotkey input: NO
Paste added: NO
Drag/drop added: NO
File dialog automation added: NO
ValuePattern write added: NO
Manual owner action required: NONE
```

Do not merge to main.
