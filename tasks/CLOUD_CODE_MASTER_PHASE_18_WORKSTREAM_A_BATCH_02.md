# CLOUD CODE MASTER TASK — PHASE 18 WORKSTREAM A BATCH 02
# SEMANTIC SAFETY HARDENING → GROUNDED NATIVE INPUT → REPEATABLE COMPUTER-USE EVALUATION

**Project:** JARVIS  
**Target agent:** Cloud Code  
**Owner:** Mahmoud  
**Date:** 2026-09-12  
**Execution style:** One master task with sequential, independently-verified milestones.  
**Branch:** `feature/phase-18-computer-use-v2`

---

# 0. PURPOSE

You are starting with **zero prior session knowledge**.

The owner explicitly wants meaningful progress per Cloud Code session, but does not want one giant unreviewable implementation.

This single master task contains three substantial milestones:

1. **Milestone 0 — harden the semantic UIA foundation after independent GitHub review**
2. **Milestone 1 — add bounded, grounded native input fallback**
3. **Milestone 2 — build and run a repeatable Computer Use V2 evaluation suite**

For every milestone:

```text
inspect only the relevant current code
→ implement that milestone
→ run focused tests
→ run the milestone regression gate
→ inspect diff/security boundaries
→ update only truthful docs
→ commit
→ push the same feature branch
→ continue only if green
```

Do not merge to `main`.

Do not squash milestones.

Do not continue past a failed milestone.

Already-pushed green milestones remain valid if a later milestone blocks.

---

# 1. EXPECTED STARTING STATE

Repository:

`MahmoudNagiubX/JARVIS`

Expected repo root:

`C:\Jarivs\00_final\jarvis`

Expected branch:

`feature/phase-18-computer-use-v2`

Expected starting HEAD:

`2390ddc7aaa7be3596826027e4cd351d919643c8`

Expected most recent Batch 01 commits:

```text
db1233f2  fix: close phase 18 checkpoint review
cd66ca32  feat: add semantic UIA foundation
357bfe0f  feat: expose semantic desktop read tools
2390ddc7  feat: add bounded semantic UI actions
```

Before any edit run:

```powershell
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git status --short
git log --oneline --decorate -10
git remote -v
```

If HEAD differs because another owner-approved commit exists, inspect it before proceeding.

If the difference is unexplained, STOP.

Never:

- reset;
- clean;
- stash owner changes;
- discard owner changes;
- amend already-pushed commits;
- force-push.

---

# 2. MINIMAL READ SET

Do **not** read the entire repository.

Read first:

1. `AGENTS.md`
2. `docs/source_of_truth/01_JARVIS_CORE_SOURCE_OF_TRUTH.md`
3. `docs/source_of_truth/03_JARVIS_GAP_REGISTER.md`
4. `docs/source_of_truth/04_JARVIS_EXECUTION_ROADMAP.md`
5. `docs/source_of_truth/05_JARVIS_DECISION_LOG.md`
6. `docs/audits/PHASE_18_WORKSTREAM_A_BATCH_01.md`

Then inspect:

### Semantic/UIA
- `src/jarvis/computer/semantic_uia.py`
- `src/jarvis/contracts/semantic_ui.py`
- `src/jarvis/perception/windows.py`
- `src/jarvis/perception/privacy.py`

### Canonical computer authority
- `src/jarvis/computer/service.py`
- `src/jarvis/contracts/computer.py`
- `src/jarvis/tools/registry.py`
- `src/jarvis/authority/permissions/engine.py`

### Evaluation
- `src/jarvis/evaluation/service.py`
- `docs/architecture/SELF_EVALUATION.md`

### Existing relevant architecture
- `docs/architecture/COMPUTER_CONTROL.md`
- `docs/architecture/GROUNDED_DESKTOP_INTERACTION.md`

### Tests
- `tests/test_phase_eighteen_semantic_uia.py`
- `tests/test_phase_eighteen_semantic_tool_path.py`
- `tests/test_phase_eighteen_semantic_actions.py`
- `tests/test_phase_eleven_windows_interaction.py`
- `tests/test_phase_ten_active_perception.py`

Only expand the read set when an actual import/caller requires it.

---

# 3. CURRENT ARCHITECTURE — DO NOT CHANGE

Preserve:

```text
AgentRuntime
→ ToolExecutionService
→ PermissionEngine
→ ApprovalEngine when needed
→ ComputerActionService
→ WindowsNativeComputerController
→ product-owned UIA/native-input adapters
→ operating system
→ independent observation/verification
→ ComputerResult / ToolResult
→ audit + events
→ model/user
```

Never create:

- second ComputerActionService;
- second PermissionEngine;
- second ApprovalEngine;
- second audit authority;
- direct model → `uiautomation`;
- direct model → `SendInput`;
- arbitrary shell/PowerShell runtime tool;
- raw COM escape hatch;
- raw HWND model action;
- raw coordinate model action.

UIA remains the primary semantic target identity.

Native input is a **fallback execution mechanism**, never a replacement for grounding.

---

# 4. GLOBAL RESTRICTIONS

This batch must preserve:

- local-first / offline-capable runtime;
- free runtime;
- no API key;
- no cloud computer-use API;
- no UAC bypass;
- no UIAccess privilege request;
- no admin requirement for ordinary targets;
- no raw secret persistence;
- no screen-content Memory writes;
- no arbitrary remote shell;
- no unrestricted filesystem widening;
- no file-dialog path entry;
- no generic UIA ValuePattern write;
- no drag/drop yet;
- no right-click/context-menu automation yet;
- no arbitrary raw coordinate click;
- no OCR/vision fallback yet.

## GAP-0503 remains a hard restriction

Do not use mouse/keyboard/UIA to work around file access policy.

Do not automate:

- Open-file path entry;
- Save-as path entry;
- file picker confirmation;
- arbitrary Explorer path access;

until GAP-0503 is separately resolved.

---

# 5. INDEPENDENT REVIEW OF BATCH 01 — REQUIRED FIXES

An independent review inspected the actual pushed GitHub commits, not only the Cloud Code report.

Batch 01 is accepted as a sound foundation, but the following issues must be closed before expanding control.

---

## R18B01-001 — weak RuntimeId fallback can collapse identity

Current implementation:

`_runtime_id_digest(control)`

returns the SHA-256 digest of `repr(())` when:

- `GetRuntimeId` is missing;
- it raises;
- it returns no usable ID.

That means every weak/unavailable RuntimeId becomes the **same digest**.

Current `_ElementRefEntry` stores additional identity hints:

- AutomationId;
- control type;
- name;
- ancestry;

but `_reresolve()` currently matches only the RuntimeId digest.

### Risk

For a consequential action, if RuntimeId is unavailable and exactly one weak-ID control exists in the bounded tree, an old element ref can potentially re-resolve to a different logical element.

Approval reduces impact but does not make wrong-target execution acceptable.

### Required outcome

Represent RuntimeId availability explicitly.

Do not hash missing identity into a fake "strong" digest.

Recommended product model:

```text
identity_strength:
  strong
  weak
```

or an equivalent internal/product-owned representation.

### Strong identity

When a non-empty valid UIA RuntimeId exists:

- store its digest;
- re-resolution must require that exact digest;
- additionally sanity-check stable semantic properties when practical.

Do not require mutable Name equality for a strong reference because legitimate controls can change Name while remaining the same UIA element.

### Weak identity

When RuntimeId is unavailable:

Read-only references may be issued if useful.

Their re-resolution must use a bounded composite:

- containing window ref;
- AutomationId if present;
- control type;
- name hint;
- bounded ancestry hints;

and must require a **unique** match.

But:

> weak-identity refs must NOT be actionable.

`invoke/toggle/select/native-click` must fail closed with a typed code such as:

`uia_element_identity_weak`

### Model visibility

Add a vendor-neutral field such as:

`actionable: bool`

to `SemanticElementSnapshot`.

Do not expose raw RuntimeId.

Do not expose its digest.

The model may know whether the ref can safely be used for action, but not provider identity internals.

### Tests

Add tests for:

- `GetRuntimeId()` raises;
- empty RuntimeId;
- two weak elements with same hints => ambiguous;
- one weak element read can re-resolve;
- weak ref actuation denied;
- strong ref remains actionable;
- strong ref never retargets to an impostor.

---

## R18B01-002 — `semantic_list_windows` bypasses sensitive-window filtering

Current adapter `list_windows()` directly returns:

`WindowsDesktopProvider.desktop_context(...)`

The provider enumerates metadata including window titles.

`validate_input_window()` enforces `PerceptionPrivacyPolicy` later for a selected window, but `list_windows()` itself currently does not filter sensitive metadata.

### Risk

The semantic read tool can expose title/process metadata for:

- login/sign-in;
- credential/password;
- private-key;
- denied system processes;

even though later tree inspection would be denied.

### Required outcome

`semantic_list_windows` must enforce the same product privacy policy.

Rules:

1. if metadata perception is disabled (`privacy mode OFF`) => deny the operation;
2. filter every window for which `check_window(process_name, title)` returns a denial;
3. never return its title/process/ref to the model;
4. optionally return only a numeric:
   - `filtered_count`
   - or `sensitive_windows_hidden`
5. do not leak which title caused the filter.

Do not weaken the existing `PerceptionPrivacyPolicy`.

### Tests

- sensitive window absent from returned list;
- normal window remains;
- privacy mode OFF denies list;
- filtered title does not appear anywhere in serialized model output.

---

## R18B01-003 — post-action verification must perform fresh re-observation

Current Batch 01 behavior:

### Toggle

Reads:

`pattern.ToggleState`

then calls:

`pattern.Toggle()`

then reads:

the **same pattern object's** `ToggleState`.

### Select

Calls:

`pattern.Select()`

then reads:

the **same pattern object's** `IsSelected`.

### Invoke

After `Invoke()` it calls `_make_snapshot()` on the original `Control`.

### Problems

This is not the strongest version of the locked:

`ACT → RE-OBSERVE → VERIFY`

contract.

Also, an invocation can legitimately:

- close its dialog;
- destroy the button;
- replace the UI tree;
- navigate to another view.

In that case the action may have succeeded, but reading the old COM object can raise after the side effect already happened.

That can produce an opaque failure after a real action, encouraging accidental retries.

### Required outcome

After the pattern call:

- never assume the original `Control`/pattern object is still valid;
- perform fresh product-owned re-resolution/observation.

#### Invoke

Generic invoke remains:

`verified=False`

unless a separate known verifier proves the post-condition.

After `Invoke()`:

- attempt fresh re-observation;
- if target is still valid, include a fresh snapshot;
- if it disappeared/became stale, do **not** throw;
- return a truthful succeeded-but-unverified receipt with a bounded verification reason such as:
  - `generic_invoke_no_postcondition`
  - `target_disappeared_after_invoke`
  - `post_observation_unavailable`

Never auto-repeat.

#### Toggle

After `Toggle()`:

- fresh re-resolve element;
- obtain a **fresh TogglePattern**;
- read fresh state;
- verified true only if the state change is supported by fresh evidence.

If target disappears:

- action may have executed;
- return succeeded/unverified, not a fabricated failure that implies nothing happened.

#### Select

After `Select()`:

- fresh re-resolve;
- obtain fresh SelectionItemPattern;
- read `IsSelected`;
- verified true only from the fresh state.

### Typed receipts

Add bounded machine-readable verification information:

- `verification_reason`
- optional `pre_state`
- optional `post_state`

Do not persist raw UI content unnecessarily.

### Tests

- invoke destroys its own control/window => no uncaught exception;
- invoke destroyed target => succeeded + verified false;
- toggle same-object cache lies but fresh object has true state => use fresh object;
- stale post-target => no retry;
- select fresh read only;
- provider exception during post-observation => truthful unverified receipt.

---

## R18B01-004 — semantic approval is not sufficiently understandable/bound to UI target lifetime

Current approval preview is built by:

`ComputerActionService._approval_preview(action)`

For semantic action parameters this effectively shows:

```text
semantic_invoke
element-<uuid>
```

That is not enough for a human owner to know what button/control is being approved.

Also:

- ComputerActionService generic approval expiry is approximately 10 minutes;
- semantic element refs default to approximately 45 seconds.

A semantic approval can therefore remain pending long after its target ref is guaranteed stale.

### Required outcome

Semantic actions need a **target-aware, time-bounded approval preview**.

Before creating a semantic approval request:

1. read/revalidate the target through the product-owned semantic boundary;
2. if it is stale/weak/sensitive/non-actionable:
   - do not create approval;
   - return typed failure;
3. construct a safe bounded preview from trusted observation:
   - action
   - control name (bounded)
   - control type
   - AutomationId if present
   - window/app label when safely available
   - element ref
   - ref expiry / approval deadline
4. never include text/value contents;
5. never include password values;
6. never trust model-supplied preview text.

### Transaction binding

Store a target identity/preview digest in the in-memory pending action record.

On approval resume:

- revalidate target;
- recompute trusted preview identity;
- if materially changed:
  - do not execute;
  - return `approval_target_changed` or equivalent;
- if stale:
  - return typed stale failure.

### Approval expiry

Semantic approval expiry must not exceed the current element reference validity.

Prefer:

```text
approval_expires_at = min(generic_approval_deadline, element_ref_expires_at)
```

The semantic adapter may expose an **internal product-owned target preview** method to ComputerActionService.

This method must not expose raw RuntimeId/COM.

### Tests

- approval preview contains bounded human-meaningful control label;
- preview contains no text/value secret;
- weak identity => no approval created;
- stale target => no approval created;
- target changes after approval request => approval resume refuses;
- approval deadline <= element ref deadline;
- normal approval still executes exactly once;
- repeated decide still cannot duplicate action.

---

## R18B01-005 — reject disabled/non-interactable targets before actuation

Before:

- invoke;
- toggle;
- select;
- native click later in Milestone 1;

the target should be checked after fresh re-resolution.

At minimum fail closed when:

- `IsEnabled` is false;
- sensitive/password;
- strong identity is unavailable.

For offscreen:

Default semantic/native click actuation should refuse `IsOffscreen=True`.

Typed code:

`uia_target_not_interactable`

or equivalent.

Later specialized adapters may support scrolling into view; this batch must not silently click an offscreen element.

---

# 6. MILESTONE 0 — SEMANTIC SAFETY HARDENING

Implement **only** R18B01-001 through R18B01-005.

Do not add mouse/keyboard fallback yet.

---

## 6.1 Keep the public architecture small

Prefer modifying:

- `contracts/semantic_ui.py`
- `computer/semantic_uia.py`
- `computer/service.py`
- related tests

Do not add a new top-level authority.

If an internal target-preview model is needed, keep it product-owned and minimal.

---

## 6.2 Physical semantic acceptance after fixes

Use a disposable test surface.

Preferred acceptance fixture:

- Microsoft Edge **Guest** window;
- local temporary HTML file under the OS temp directory;
- delete temporary file after acceptance;
- no owner browser profile;
- no login;
- no internet dependency.

Fixture should contain only inert local controls such as:

- button that changes a local status label;
- checkbox;
- `<select>` with two options;
- status element.

Use it to attempt physical proof of:

- invoke;
- toggle;
- select.

Every action must go through:

`computer.semantic.act`

and normal approval.

Never call `uiautomation` directly for acceptance.

### If Chromium does not expose the required pattern

Do not fabricate success.

Try another safe disposable local control surface.

If no physical TogglePattern/SelectionItemPattern target is available:

- keep code/test acceptance;
- mark physical acceptance pending;
- continue only if the implementation itself is green.

---

## 6.3 Milestone 0 tests

Run/add focused tests for all review findings.

Expected test modules include:

- semantic UIA;
- semantic actions;
- semantic tool path;
- approval integration.

Then:

```powershell
python -m pytest tests -k "phase_eighteen" -q
python -m pytest tests -q
python -m compileall src tests -q
git diff --check
```

Frontend may be deferred until final batch if untouched.

---

## 6.4 Milestone 0 docs

Create/append the Batch 02 report:

`docs/audits/PHASE_18_WORKSTREAM_A_BATCH_02.md`

Also minimally update current-state/gap/roadmap only if behavior truth changed.

Do not close GAP-0101 until this independent-review hardening is green and physical evidence is honestly evaluated.

---

## 6.5 Milestone 0 commit

Commit:

`fix: harden semantic computer-use targets`

Push same feature branch.

Record:

`MILESTONE_0_COMMIT`

Continue only if push succeeds.

---

# 7. MILESTONE 1 — GROUNDED NATIVE INPUT FALLBACK

## Goal

Add real native Windows input as a **fallback** when semantic patterns are unavailable.

This milestone advances GAP-0102 without creating coordinate-first automation.

---

# 7.1 Architectural rule

Native input may act only after grounding.

For mouse:

```text
element_ref
→ semantic revalidation
→ strong/actionable target
→ containing window ref
→ privacy/interactable checks
→ verified foreground window
→ fresh element bounds
→ native SendInput
→ post-observation
```

The model must never supply:

- x;
- y;
- HWND;
- raw virtual-key code;
- raw Win32 flags.

---

# 7.2 Product-owned native input adapter

Do not scatter additional `SendInput` logic through many service methods.

Preferred design:

`src/jarvis/computer/native_input.py`

with a product-owned adapter such as:

`WindowsNativeInputAdapter`

This is an execution provider, **not an authority**.

It remains behind:

`ComputerActionService`.

### Existing keyboard input

Current literal `type_text` already uses native SendInput inside the Windows controller.

Avoid ending with two incompatible low-level input implementations.

Preferred:

- move reusable SendInput primitives into one native-input adapter;
- preserve current public literal typing behavior exactly;
- keep existing tests green.

If moving existing code would create high-risk broad churn, keep the behavior in place but make new primitives share the same internal low-level helper rather than copy/paste another SendInput stack.

No second input authority.

---

# 7.3 Mouse support — deliberately bounded

Implement only:

1. `move_to_element`
2. `left_click_element`

Do NOT implement yet:

- raw coordinate move;
- raw coordinate click;
- right click;
- double click;
- drag/drop;
- wheel scrolling.

---

## 7.3.1 Targeting

The tool/API accepts:

`element_ref`

only.

Before native input:

- semantic ref must be strong/actionable;
- element must be enabled;
- element must not be offscreen;
- fresh bounds must exist;
- containing window must pass privacy policy;
- containing window must be focused;
- `GetForegroundWindow` must confirm the same target window;
- target must be revalidated again after focus because focus can change layout.

---

## 7.3.2 Coordinates

Coordinates are provider-internal only.

Use the center of the **fresh** element bounds.

Validate it lies inside the Windows virtual desktop.

Current Windows provider already uses virtual desktop metrics:

```text
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79
```

Absolute SendInput coordinates must be normalized to:

`0..65535`

against the **entire virtual desktop**, not only the primary monitor.

Use Windows SendInput mouse flags:

- `MOUSEEVENTF_MOVE`
- `MOUSEEVENTF_ABSOLUTE`
- `MOUSEEVENTF_VIRTUALDESK`

for movement.

For click:

- move;
- LEFTDOWN;
- LEFTUP;

in one bounded SendInput batch where practical.

Do not use deprecated `mouse_event`.

Do not use `SetCursorPos` as the action implementation.

---

## 7.3.3 Verification

### Move

After movement, `GetCursorPos` may verify pointer position within a tiny pixel tolerance.

A verified pointer location means only:

> pointer reached grounded target coordinates

not:

> application action succeeded.

### Left click

SendInput delivery alone does not prove the application performed the intended semantic action.

Generic click should normally be:

`succeeded, verified=False`

with bounded evidence such as:

- input batch accepted;
- pointer target verified;
- target window remained foreground;
- post semantic observation available/unavailable.

If a separate evaluator independently observes the desired post-condition, that **scenario** may be proven successful.

Never mark generic click `verified=True` solely because SendInput accepted all events.

---

# 7.4 Windows SendInput / UIPI safety

Windows SendInput is subject to UIPI.

Normal processes can inject only into equal/lower integrity targets.

Failure does not reliably identify UIPI as the cause.

Therefore:

- do not elevate JARVIS;
- do not request UIAccess;
- do not bypass UIPI;
- if SendInput is partial/zero, return a generic typed input failure;
- do not falsely state "UIPI blocked" unless separately proven.

Suggested code:

`native_input_injection_failed`

Keep diagnostics bounded.

---

# 7.5 User interference / key state

Before native keyboard injection:

Use `GetAsyncKeyState` or equivalent bounded check for modifier keys.

If the real user is physically holding:

- Shift;
- Ctrl;
- Alt;
- Windows key;

and that could alter the requested operation:

fail safely with:

`native_input_modifier_state_unsafe`

Do not attempt to "correct" the owner's currently-held keys by synthesizing releases for physical input JARVIS did not create.

Any modifier JARVIS presses itself must be released in the same bounded SendInput batch / guaranteed cleanup path.

---

# 7.6 Bounded named key input

Add a new grounded key action.

Initial named-key allowlist:

```text
tab
enter
escape
space
left
right
up
down
home
end
page_up
page_down
backspace
delete
```

Optionally support:

`shift+tab`

through a product-owned bounded modifier enum.

Do not allow:

- raw VK integer;
- arbitrary scan code;
- Windows key;
- Ctrl+Alt+Delete;
- arbitrary free-form hotkey string.

If a clean bounded modifier representation is implemented, restrict modifiers to a small enum and validated combinations.

All named-key input remains:

- target-window grounded;
- foreground verified;
- consequential / approval-required.

Do not auto-allow Enter/Delete merely because they are named.

---

# 7.7 Existing literal text input

Do not remove the current:

`computer.keyboard.type`

behavior.

Preserve:

- Unicode literal text;
- max length;
- foreground re-check per chunk;
- ephemeral argument retention;
- approval behavior.

Do not add paste as a shortcut in this batch.

---

# 7.8 Native-input tools

Expose a minimal surface.

Preferred conceptual tool shape:

### Pointer

`computer.pointer.act`

Actions:

- `move_to_element`
- `left_click_element`

Parameters:

- `element_ref`
- optional target device

No coordinates.

### Key

Either extend the existing keyboard tool safely or add:

`computer.keyboard.key`

Parameters:

- `window_ref`
- `key`
- optional bounded modifier(s)
- target device

No raw code.

Follow existing tool-selection conventions to keep model schema small.

Arguments that represent side effects must remain ephemeral.

---

# 7.9 Risk / approvals

### Move pointer

Although pointer movement is reversible, it can trigger hover behavior.

Treat as consequential for this initial milestone unless the existing risk model has a clear lower-risk class that still passes canonical policy.

### Click

Approval-required.

### Key press

Approval-required.

No native-input action may bypass `ComputerActionService`.

---

# 7.10 Native-input tests

Required deterministic tests:

## Coordinate math

- primary monitor origin;
- negative virtual desktop X/Y;
- second-monitor-like coordinate;
- exact edges;
- one-pixel width/height defensive math;
- out-of-bounds target rejected;
- no raw coordinate accepted by tool schema.

## Mouse

- strong element ref required;
- weak ref denied;
- disabled denied;
- offscreen denied;
- stale denied;
- containing window foreground verified;
- target revalidated after focus;
- SendInput partial count => failure;
- pointer position mismatch => no verified move;
- left click never generic verified true from input delivery alone.

## Keyboard

- key allowlist enforced;
- raw VK denied;
- unsupported key denied;
- modifier currently held => fail safely;
- JARVIS-generated modifiers always released;
- foreground change => no injection;
- SendInput partial => failure;
- approval required.

## Architecture

- through ComputerActionService;
- PermissionEngine reached;
- ApprovalEngine reached;
- audit exists;
- no filesystem field in schemas;
- no raw x/y/VK/HWND model schema.

---

# 7.11 Physical native-input acceptance

Use only disposable apps.

Preferred:

- Calculator;
- the same disposable Edge Guest/local HTML fixture from Milestone 0.

Required attempts:

## Element-grounded click

Use a local fixture control whose click changes a local status label.

Path:

```text
find element
→ request native left click
→ approval required
→ approve
→ native SendInput click
→ independent semantic read of status label
```

The independent evaluator may declare the **scenario** PASS if status changed.

The generic click result itself must remain honestly unverified unless product-level verifier evidence is integrated.

## Named key

Use a harmless fixture with at least two focusable controls.

Example:

- focus guest fixture window;
- press Tab through JARVIS native key action;
- independent semantic observation confirms focus moved.

No owner document editing.

No owner's browser profile.

---

# 7.12 Milestone 1 verification

Focused native input + semantic regression:

```powershell
python -m pytest tests -k "phase_eighteen or phase_eleven or phase_ten" -q
python -m pytest tests -q
python -m compileall src tests -q
git diff --check
```

Frontend can wait until final batch if untouched.

---

# 7.13 Milestone 1 docs

Update Batch 02 report.

Canonical truth:

- GAP-0102 becomes `PARTIAL` if grounded click + named key path is implemented/proven;
- do not mark complete because drag/drop/right click/scroll/richer hotkeys/paste remain absent;
- GAP-0106 may get evidence notes but is not automatically resolved.

---

# 7.14 Milestone 1 commit

Commit:

`feat: add grounded native input fallback`

Push.

Record:

`MILESTONE_1_COMMIT`

Continue only if green.

---

# 8. MILESTONE 2 — REPEATABLE COMPUTER-USE EVALUATION SUITE

## Goal

Stop relying only on ad-hoc manual probe scripts.

Build a repeatable, local, product-owned evaluation layer for Computer Use V2.

Reuse the existing:

`EvaluationService`

Do not create `ComputerUseEvaluationServiceV2`.

---

# 8.1 Deterministic evaluation suite

Add a product-owned suite, for example:

`computer_use_v2`

using:

- `EvaluationCase`
- `RegressionSuite`
- existing EvaluationService persistence/events

The suite should be runnable without a GUI using fakes/mocks and should cover contracts rather than physical OS success.

Minimum deterministic cases:

1. semantic read uses canonical authority
2. sensitive window does not leak
3. weak UIA identity cannot actuate
4. stale target cannot actuate
5. approval target-change binding works
6. semantic act requires approval
7. post-action verification never trusts only the stale original object
8. generic invoke remains unverified without postcondition
9. toggle/select use fresh evidence
10. native pointer requires grounded element
11. native key requires grounded foreground window
12. raw coordinates rejected
13. raw VK rejected
14. no filesystem parameter introduced
15. model-visible `verified` survives
16. UI text cannot self-authorize
17. wrong-target execution count remains zero in fixture cases

Do not duplicate all unit tests inside EvaluationService.

Evaluation cases should represent meaningful product acceptance contracts.

---

# 8.2 Evaluation metrics

Track metrics that matter for Computer Use:

- success/pass rate
- wrong action count
- policy bypass count
- stale-target refusal
- verified-success correctness
- unverified-success count
- steps/actions used
- re-observation count
- latency where available

Do not invent "confidence" percentages without evidence.

---

# 8.3 Physical acceptance runner

Create a durable development script under the existing scripts hierarchy, for example:

`scripts/phase18/computer_use_acceptance.py`

Do not put it in production AgentRuntime.

It must:

- be explicit opt-in;
- refuse on non-Windows;
- use only disposable fixtures it creates;
- never enumerate/interact with unrelated owner windows beyond what is necessary to identify its own fixture;
- never use owner browser profile;
- clean up its own processes/temp files;
- output a concise structured summary;
- not persist raw UI text.

Preferred fixtures:

## Calculator

Use for:

- semantic invoke;
- display read-back.

## Edge Guest local fixture

Use a temporary local HTML page with:

- inert button
- checkbox
- select
- focusable controls
- status label

Use for:

- invoke
- toggle
- select
- native left click
- Tab/focus key behavior

No network dependency.

Delete temporary file after completion.

If Edge is unavailable:

- use another safe local disposable surface;
- do not interact with the owner's normal browser profile.

---

# 8.4 Required repeated physical runs

Run the physical acceptance suite at least:

`3`

times in the same clean session where practical.

Record:

- passes/attempts for each scenario;
- wrong targets;
- approval behavior;
- verification evidence;
- latency.

Do not hide flaky results.

If a scenario passes 2/3, report 2/3.

No retry-until-green loop.

---

# 8.5 Toggle/Select physical proof

This milestone should attempt to close the physical evidence missing from Batch 01.

The local Edge Guest fixture may expose:

- checkbox-like TogglePattern;
- selection/list pattern.

Accessibility mappings can differ by Chromium/Windows version.

If real UIA does not expose those patterns:

- record exact observed pattern set;
- keep physical acceptance pending;
- do not alter production code merely to force the test.

---

# 8.6 Multi-monitor / DPI evidence

## Unit-level requirements

Native coordinate conversion must be tested for virtual desktop geometries including:

- negative X origin;
- negative Y origin;
- extended desktop dimensions.

## Physical environment

Record actual NIGHTFURY:

- virtual desktop origin;
- virtual desktop width/height;
- number of monitors if safely queryable;
- current DPI for fixture window if available through normal Win32 API.

Do not alter display settings.

If NIGHTFURY currently has multiple monitors:

attempt safe fixture interactions on the non-primary monitor if practical.

If there is only one monitor:

record:

`MULTI_MONITOR_PHYSICAL_PENDING`

Do not fail the entire batch solely because the hardware topology is unavailable.

## DPI

Do not manually rescale UIA bounding rectangles without evidence.

Use actual UIA screen bounds and virtual-desktop coordinate mapping.

If a real non-100% DPI monitor/config is available, physically test.

Otherwise keep DPI physical proof partial.

---

# 8.7 Secure desktop / UIPI evidence

Do NOT deliberately trigger UAC just to automate it.

Do NOT request elevation.

Required evidence:

- policy/unit tests for sensitive/secure windows;
- SendInput zero/partial return produces truthful failure;
- docs state UIPI can block higher-integrity targets;
- JARVIS does not bypass it.

GAP-0106 remains open unless real environment evidence supports closure.

---

# 8.8 Evaluation integration

Register the deterministic Computer Use suite through the existing evaluation registry/bootstrap pattern if that is how default suites are exposed.

Do not load physical fixtures during normal runtime startup.

The physical runner is opt-in development/evaluation only.

Evaluation results may be durable through the existing EvaluationService schema, but raw UI contents must not be stored.

---

# 8.9 Milestone 2 tests

Add deterministic tests for:

- suite registration
- evaluation pass/fail
- regression detection if applicable
- no physical test runs by default
- raw UI data not persisted
- physical runner refuses non-Windows / unsafe preconditions
- fixture cleanup path

Then run:

```powershell
python -m pytest tests -k "evaluation or phase_eighteen" -q
python -m pytest tests -q
python -m compileall src tests -q
git diff --check
```

Final frontend gate:

```powershell
cd ui
npm test
npm run build
npm audit --audit-level=high
cd ..
```

---

# 8.10 Canonical status after evaluation

Update:

- `02_JARVIS_CURRENT_STATE.md`
- `03_JARVIS_GAP_REGISTER.md`
- `04_JARVIS_EXECUTION_ROADMAP.md`

Only based on real evidence.

## GAP-0101

May become `RESOLVED` only if:

- independent-review hardening is closed;
- strong action identity is enforced;
- sensitive-window leak is closed;
- fresh post-action observation exists;
- approvals are target-aware;
- invoke/toggle/select code paths are green;
- meaningful physical evidence exists.

If Toggle/Select physical proof remains unavailable, do not overclaim.

## GAP-0102

Expected:

`PARTIAL`

after grounded left click + named key support.

## GAP-0104

Expected:

`PARTIAL/OPEN`

because this batch improves:

- stale handling;
- post-action evidence;
- wrong-target refusal;

but does not build full autonomous multi-app replan logic.

## GAP-0105

Can become `PARTIAL` or `RESOLVED_FOUNDATION`.

Do not mark the entire broad evaluation gap resolved unless the repeatable suite genuinely covers the representative apps/failures named in the gap.

## GAP-0106

Likely remains `OPEN/PARTIAL`.

## GAP-0503

Remains `OPEN`.

---

# 8.11 Milestone 2 commit

Commit:

`test: add computer-use evaluation suite`

Push same branch.

Record:

`MILESTONE_2_COMMIT`

No merge.

---

# 9. FINAL BATCH GATE

After Milestone 2 push:

```powershell
git status -sb
git log --oneline --decorate -12
git diff main...HEAD --stat
```

Expected new commits from Batch 02:

1. `fix: harden semantic computer-use targets`
2. `feat: add grounded native input fallback`
3. `test: add computer-use evaluation suite`

Exact SHAs must be returned.

---

# 10. FINAL FULL VERIFICATION

At final branch HEAD:

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

Also verify explicitly:

- no `shell=True`;
- no `os.system`;
- no direct model-to-UIA/native-input path;
- no raw COM in public contracts;
- no raw HWND in model schema;
- no raw x/y in model schema;
- no raw VK/scan code in model schema;
- no weak-identity actuation;
- no stale target actuation;
- no sensitive list-window leakage;
- no opaque semantic approval preview;
- semantic approval expiry bounded by reference life;
- no same-object-only post-action verification;
- no auto retry after uncertain action;
- no UIAccess/elevation request;
- no GAP-0503 bypass;
- no file-dialog path entry;
- no ValuePattern write;
- no drag/drop/right click;
- no raw owner browser profile use;
- no owner document mutation in physical testing;
- no secrets in repo/logs/reports.

---

# 11. BATCH 02 REPORT

Create one report:

`docs/audits/PHASE_18_WORKSTREAM_A_BATCH_02.md`

Do not create repetitive milestone reports.

Required sections:

1. Starting branch/HEAD
2. Independent review findings
3. Milestone 0
   - strong/weak identity
   - privacy
   - fresh verification
   - approval target binding/TTL
   - interactability
   - physical semantic acceptance
   - tests
   - commit
4. Milestone 1
   - native input architecture
   - mouse
   - keyboard
   - virtual desktop math
   - UIPI handling
   - physical acceptance
   - tests
   - commit
5. Milestone 2
   - deterministic evaluation suite
   - physical runner
   - 3-run results
   - monitor/DPI evidence
   - secure/UIPI evidence
   - tests
   - commit
6. Final regression
7. Security review
8. Gap status
9. Manual dependencies
10. Restrictions remaining
11. Recommended Batch 03

---

# 12. MANUAL OWNER ACTION

Expected:

`NONE`

No API key/account/token is needed.

GitHub push auth is assumed already configured because prior batch push succeeded.

If physical acceptance needs the owner to manually move a fixture to another monitor because automated safe placement is not possible, do not block the batch.

Record:

`OPTIONAL_PHYSICAL_MULTI_MONITOR_STEP`

but continue with unit-level evidence and mark physical multi-monitor pending.

Do not ask for passwords or credentials.

---

# 13. STOP CONDITIONS

Stop the current and later milestones if:

- starting branch/HEAD is unexplained;
- strong identity cannot be made fail-closed;
- wrong-target actuation is observed;
- sensitive-window metadata still leaks;
- semantic approval cannot be bound to target identity;
- target preview would require persisting secrets/raw values;
- fresh post-action re-observation cannot be implemented safely;
- native input requires raw model coordinates;
- normal native input requires elevation/UIAccess;
- SendInput implementation cannot protect foreground target;
- file-access authority must be widened;
- full suite gains unexplained failures;
- new P0/P1 security defect appears;
- push fails due credentials.

Keep prior green pushed milestones.

Never partially commit a failed milestone.

---

# 14. GIT RULES

Each milestone:

- explicit `git add <paths>`;
- no `git add .`;
- inspect staged diff;
- commit only after green gate;
- push immediately;
- no amend after push;
- no rebase/squash;
- no force;
- no push to main;
- no merge.

Task file to commit:

`tasks/CLOUD_CODE_MASTER_PHASE_18_WORKSTREAM_A_BATCH_02.md`

Commit it with Milestone 0.

---

# 15. FINAL RESPONSE FORMAT

Return one:

`PHASE18_COMPUTER_USE_BATCH02_PASS`

`PHASE18_COMPUTER_USE_BATCH02_PARTIAL`

`PHASE18_COMPUTER_USE_BATCH02_BLOCKED`

Then:

```text
Branch:
Starting HEAD:
Final HEAD:

Independent review findings closed:

Milestone 0:
Commit 0:
Focused tests 0:
Full tests 0:
Physical semantic acceptance:

Milestone 1:
Commit 1:
Focused tests 1:
Full tests 1:
Native mouse acceptance:
Native key acceptance:

Milestone 2:
Commit 2:
Focused tests 2:
Full tests 2:
Evaluation suite:
Physical repeated runs:
Multi-monitor/DPI:
Secure/UIPI:

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

Raw coordinate model input added:
Raw VK model input added:
ValuePattern write added:
File-dialog automation added:
Manual owner action required:

Next recommended batch:
Report:
```

Expected safety values:

```text
Raw coordinate model input added: NO
Raw VK model input added: NO
ValuePattern write added: NO
File-dialog automation added: NO
```

Do not merge to main.
