# CLOUD CODE TASK — PHASE 18A.2 STABILIZATION FIXES

**Project:** JARVIS  
**Task type:** Controlled stabilization / targeted fixes  
**Target agent:** Cloud Code  
**Owner:** Mahmoud  
**Date:** 2026-09-12

---

## 0. Mission

You are starting with **zero prior context** about JARVIS.

Your job is to perform a **small, evidence-driven stabilization pass** after the completed Phase 18A.1 baseline audit.

Do **not** implement Computer Use V2 yet.

Do **not** redesign architecture.

Do **not** opportunistically refactor unrelated code.

Fix only the explicitly approved findings in this task, add focused regression tests, run the required verification, update canonical project state, and stop.

The baseline audit verdict was:

`AUDIT_GATE_PASS_WITH_ROADMAP_GAPS`

Audited baseline HEAD:

`54b67ba396ec45180f1b60ea472ef94c9ac181a9`

Audit report:

`docs/audits/PHASE_18A1_BASELINE_AUDIT.md`

---

# 1. Bootstrap — zero-context agent rules

First determine the real repository root:

```powershell
git rev-parse --show-toplevel
git status --short
git branch --show-current
git rev-parse HEAD
```

Expected repo root from the audit:

`C:\Jarivs\00_final\jarvis`

Expected branch:

`main`

Do not assume the worktree is perfectly clean. The audit task/report and source-pack files may be untracked because Phase 18A.1 was intentionally audit-only.

Do not delete owner files.

Do not reset, checkout, clean, stash, or discard owner changes.

If there are unrelated modified tracked files that you cannot safely attribute to this task, stop implementation and report the exact paths.

---

# 2. Critical bootstrap anomaly — fix first

The Phase 18A.1 audit found that the canonical source pack was placed one directory above the actual git repository.

The current canonical files may exist at:

- `C:\Jarivs\AGENTS.md`
- `C:\Jarivs\docs\source_of_truth\...`

while the actual repo is:

- `C:\Jarivs\00_final\jarvis\`

This is finding **F18A1-013 / GAP-0002**.

## Required behavior

### 2.1 Before editing code

If repo-root `AGENTS.md` and `docs/source_of_truth/*` are missing:

1. Read the external copies only as a temporary bootstrap source.
2. Copy the canonical pack **unchanged** into the actual git repository:
   - `<repo>/AGENTS.md`
   - `<repo>/docs/source_of_truth/00_JARVIS_START_HERE.md`
   - `<repo>/docs/source_of_truth/01_JARVIS_CORE_SOURCE_OF_TRUTH.md`
   - `<repo>/docs/source_of_truth/02_JARVIS_CURRENT_STATE.md`
   - `<repo>/docs/source_of_truth/03_JARVIS_GAP_REGISTER.md`
   - `<repo>/docs/source_of_truth/04_JARVIS_EXECUTION_ROADMAP.md`
   - `<repo>/docs/source_of_truth/05_JARVIS_DECISION_LOG.md`
   - `<repo>/docs/source_of_truth/06_ACTIVE_WORK_PACKET_PHASE_18A.md` if present
3. From that point onward, the **repo-local copies are authoritative** for agents.
4. Do not delete or modify the parent-directory copies during this task.
5. Do not create a second source-of-truth hierarchy.

If the repo-local source pack already exists, verify it and do not duplicate it.

---

# 3. Mandatory read order

After the repo-local pack exists, read in this order:

1. `AGENTS.md`
2. `docs/source_of_truth/00_JARVIS_START_HERE.md`
3. `docs/source_of_truth/01_JARVIS_CORE_SOURCE_OF_TRUTH.md`
4. `docs/source_of_truth/02_JARVIS_CURRENT_STATE.md`
5. `docs/source_of_truth/03_JARVIS_GAP_REGISTER.md`
6. `docs/source_of_truth/04_JARVIS_EXECUTION_ROADMAP.md`
7. `docs/source_of_truth/05_JARVIS_DECISION_LOG.md`
8. `docs/audits/PHASE_18A1_BASELINE_AUDIT.md`
9. Task-specific implementation files/tests referenced below.

The actual current repository code/tests remain implementation truth.

If documentation conflicts with current code, record the conflict and preserve locked architecture unless the owner explicitly approved a change.

---

# 4. Scope — approved fixes only

Fix these findings, in this order:

1. **F18A1-013** — source-of-truth pack not inside repo.
2. **F18A1-003** — `verified` signal is dropped before the model-facing tool result.
3. **F18A1-001** — device revocation can swallow credential-revocation failure and still report success.
4. **F18A1-002** — Home Assistant action verification is HTTP-status-only.
5. **F18A1-009** — Home Assistant write-path provider exception is not converted into a truthful typed failure.
6. **F18A1-007** — `ComputerActionService.decide()` can raise raw `KeyError` for missing in-memory pending approvals.
7. **F18A1-012** — missing regression test for the real 2 MB browser page-size cap.

Do not fix unrelated P2/P3 findings unless a change is strictly necessary to make one of the approved fixes correct.

---

# 5. Explicitly deferred findings

Do **not** implement these in this task:

- F18A1-004 — NotificationService durability
- F18A1-005 — SQLite lock/contention hardening
- F18A1-006 — mission restart/approval reconciliation redesign
- F18A1-008 — atomic automation trigger claim
- F18A1-010 — general file-root confinement / sensitive-path policy
- F18A1-011 — outer ToolSpec risk metadata cleanup
- F18A1-014 — historical Master archive location

These remain roadmap work.

Important safety constraint:

**Do not expand file/system access during this task.**
Computer Use V2 must not widen arbitrary filesystem access before GAP-0503/F18A1-010 is handled in its designated workstream.

---

# 6. Fix requirements

## 6.1 F18A1-003 — propagate verification truth to the model

Audit evidence points to:

- `src/jarvis/agents/runtime/runtime.py`
- `src/jarvis/tools/service.py`
- `src/jarvis/tools/registry.py`

### Required outcome

When a tool result has a verification state, the model-facing bounded tool message must include a **machine-readable verification field**.

At minimum distinguish:

- `verified: true`
- `verified: false`
- verification unavailable/unknown, if the existing result contract supports that state

Do not rely only on natural-language wording.

Do not let the model infer verification from HTTP status, handler success, or the absence of an error.

Preserve bounded context behavior.

Preserve audit/event retention behavior.

Do not expose secret/sensitive raw arguments.

### Required tests

Add focused tests proving:

1. verified=True reaches the model-visible tool result.
2. verified=False reaches the model-visible tool result.
3. existing error handling remains bounded and correct.
4. secret/ephemeral arguments remain redacted/not exposed.

---

## 6.2 F18A1-001 — device revocation must fail truthfully

Audit evidence points to:

- `src/jarvis/devices/fabric.py`
- `src/jarvis/persistence/repositories.py`
- `src/jarvis/authority/identity/service.py`

### Current defect

A failure in `repository.revoke_device(...)` can be swallowed while:

- `device_fabric.status` is already REVOKED,
- audit/events say the device is revoked,
- the underlying credential may remain valid.

### Required outcome

A revocation operation must never report authoritative success while the credential used by `IdentityService.authenticate()` remains active.

Use the smallest architecture-consistent fix.

Preferred properties:

- fail closed;
- no swallowed security-critical exception;
- no false `device.revoked` success audit/event;
- durable state remains logically consistent;
- preserve the single identity/device authority.

Do not introduce a second revocation authority.

### Required tests

At minimum:

1. force the credential revocation persistence step to fail;
2. assert the service does **not** report successful revocation;
3. assert it does **not** emit a false successful revocation event/audit;
4. assert credential/device state does not become misleadingly split, or is rolled back/reconciled consistently;
5. keep existing happy-path revocation tests green.

---

## 6.3 F18A1-002 — Home Assistant verification must be independent

Audit evidence points to:

- `src/jarvis/devices/home/service.py`

### Current defect

`HomeAssistantTransport.execute()` effectively treats HTTP 2xx as verified success.

### Required outcome

HTTP acceptance and target-state verification must be distinct.

After a state-changing Home Assistant action:

1. perform the bounded outbound action;
2. perform an independent bounded state read-back;
3. compare actual state against the intended effect when the action has a verifiable state;
4. report `verified=True` only when independent evidence supports it;
5. otherwise return honest unverified/failed semantics according to the existing result model.

Do not claim physical proof from an HTTP response.

Do not create an infinite polling loop.

Keep retries/timeouts bounded.

If some service calls cannot be deterministically state-verified, represent that truthfully rather than inventing success.

### Required tests

At minimum:

- POST returns 2xx + state changes as intended → verified.
- POST returns 2xx + state does not change → not verified.
- read-back unavailable → no false verified success.
- unsupported/non-verifiable action → truthful bounded result.

No live Home Assistant token is required for these unit/integration tests.

---

## 6.4 F18A1-009 — Home write-path exceptions must degrade truthfully

Same implementation area as F18A1-002.

### Required outcome

Network/provider failures such as connection refused, timeout, or URL/provider exception must not escape as opaque uncaught exceptions from the canonical Home action path.

Convert them to the existing typed truthful failure shape.

Do not return success.

Do not hide useful error codes from audit/debug surfaces.

Do not expose secrets/tokens.

### Required tests

Simulate the outbound write provider raising and assert:

- no uncaught provider exception at the service boundary;
- typed failed result;
- stable error code;
- no `verified=True`.

---

## 6.5 F18A1-007 — typed computer approval failure after restart/stale decision

Audit evidence points to:

- `src/jarvis/computer/service.py`

Compare existing truthful patterns in Browser/Home approval paths before changing behavior.

### Current defect

Missing/stale in-memory pending action may raise raw `KeyError`.

### Required outcome

Return a typed failure result consistent with the canonical ComputerAction result contract.

A stale/missing pending approval must:

- not cause HTTP 500 through a raw KeyError;
- not execute the action;
- not claim success;
- remain auditable/debuggable.

Prefer an existing error-code naming convention if one already exists.

Do not invent a second approval engine.

### Required tests

At minimum:

- fresh service instance + existing/stale approval ID;
- repeated decide after pending item was already consumed;
- both return typed failure;
- neither performs the action.

---

## 6.6 F18A1-012 — browser 2 MB cap regression test

Audit evidence points to:

- `src/jarvis/browser/service.py`

Do not change the existing 2,000,000-byte production bound unless a failing test proves it is wrong.

### Required test

Inject a response/body larger than the cap and prove the browser returns the existing truthful `page_too_large` failure instead of:

- silent truncation;
- success with garbage;
- unbounded memory behavior.

This should be a test-only change unless implementation behavior fails.

---

# 7. Do not turn this into a refactor

Forbidden in this task:

- architecture rewrite;
- renaming canonical services;
- creating parallel authority services;
- replacing SQLite;
- replacing AgentRuntime;
- replacing EventBus/Scheduler;
- new orchestration framework;
- new agent swarm;
- new model provider;
- new browser framework;
- Computer Use V2 implementation;
- general file-system permission redesign;
- live integrations/API keys;
- VENOM/Home/MQTT physical setup;
- dependency upgrades unrelated to the approved findings;
- broad formatting/lint churn;
- mass file moves beyond the canonical source-pack integration.

Keep diffs small and reviewable.

---

# 8. Manual dependencies / secrets

This task requires **no owner API key, OAuth credential, SSH credential, Home Assistant token, MQTT credential, or personal data**.

Do not ask the owner for any secret.

Do not create fake credentials.

Do not add secrets to:

- repository files;
- tests;
- Markdown;
- Memory;
- logs;
- fixtures.

Use mocks/fakes for provider behavior.

If you unexpectedly discover a true blocking secret requirement, stop that specific subtask and record a `MANUAL_GATE` rather than bypassing it.

---

# 9. Verification strategy

Run focused tests after each fix.

Then run the full required baseline.

## Python

Use the environment that faithfully reproduces the project test suite.

Required:

```powershell
python -m pytest tests -q
python -m compileall src tests -q
git diff --check
```

Also run focused tests for all changed domains.

## Frontend

Even though this task should not modify frontend code, preserve baseline:

```powershell
cd ui
npm test
npm run build
npm audit --audit-level=high
cd ..
```

Expected historical baseline before this task:

- Python: 515 passed / 0 skipped / 36 subtests in the Phase 18A.1 environment
- frontend Vitest: 75 passed
- frontend build: clean
- npm high/critical: 0
- compileall: pass
- git diff --check: pass

Environment-dependent skip/pass variation is acceptable only if explained with evidence.

---

# 10. Security regression checks

Before finishing, explicitly verify:

- zero `shell=True` added;
- zero `os.system` added;
- no raw secret persistence introduced;
- no new permission/approval bypass;
- no UI/backend direct side-effect bypass;
- no new duplicate authority;
- no false `verified=True` path introduced;
- no unbounded retry/poll loop;
- no hidden broad exception swallow on security-critical paths;
- no arbitrary architecture expansion.

---

# 11. Documentation updates required

After implementation/tests are green, update the canonical repo-local source documents minimally.

## 11.1 Gap Register

Update:

`docs/source_of_truth/03_JARVIS_GAP_REGISTER.md`

Required:

- mark GAP-0002/F18A1-013 resolved only after the pack exists inside the repo;
- record F18A1-001;
- record F18A1-003;
- attach F18A1-002 evidence to the verifier/verification gap family;
- record F18A1-007/F18A1-009 status appropriately;
- leave deferred findings open;
- do not renumber established Gap IDs unnecessarily.

If exact ID allocation is ambiguous, preserve the audit finding IDs and add them under the nearest existing gap family instead of inventing a conflicting numbering scheme.

## 11.2 Current State

Update:

`docs/source_of_truth/02_JARVIS_CURRENT_STATE.md`

Only update facts that materially changed because of this task.

Do not claim Computer Use V2 is implemented.

Do not claim Home Assistant is physically configured.

Do not claim physical acceptance.

## 11.3 Roadmap

Update:

`docs/source_of_truth/04_JARVIS_EXECUTION_ROADMAP.md`

Reflect:

- Phase 18A.1 audit completed;
- Phase 18A.2 targeted stabilization completed if all approved fixes pass;
- deferred findings remain in their appropriate later workstreams;
- next candidate becomes Workstream A — Computer Use V2.

## 11.4 Decision Log

Update `05_JARVIS_DECISION_LOG.md` only if this task makes a real new architecture/product decision.

Routine bug fixes do **not** require new DEC entries.

---

# 12. Required task report

Create:

`docs/audits/PHASE_18A2_STABILIZATION.md`

Include:

1. exact starting HEAD;
2. exact ending worktree state;
3. files changed;
4. each approved finding:
   - root cause,
   - fix,
   - tests,
   - final status;
5. deferred findings explicitly not touched;
6. all verification commands/results;
7. any manual gates;
8. architecture/security regression check;
9. final recommendation for Computer Use V2.

Use exact evidence, not vague statements.

---

# 13. Git rules

Do not push.

Do not merge.

Do not force-reset.

Do not rewrite history.

Do not create or delete branches unless explicitly required by the owner's existing workflow.

A local commit is **not required** by this task unless the owner explicitly asked Cloud Code to commit.

If you do create a commit because the owner's environment/workflow explicitly requires it, use one small stabilization commit and report the hash. Otherwise leave the reviewed diff for owner approval.

---

# 14. Stop conditions

Stop and report rather than improvising if:

- implementation truth contradicts a locked architecture decision in a way that requires redesign;
- a fix would require creating a second authority;
- a fix needs a real credential/secret;
- an unrelated tracked owner change makes the affected file unsafe to edit;
- tests expose a broader architectural defect outside the approved scope;
- the source-of-truth copies differ materially and you cannot determine which is newer from evidence.

Do not silently choose a new architecture.

---

# 15. Success criteria

This task is complete only if:

- repo-local source-of-truth bootstrap exists and is authoritative for future agents;
- F18A1-003 is fixed and tested;
- F18A1-001 is fixed and tested;
- F18A1-002 is fixed and tested;
- F18A1-009 is fixed and tested;
- F18A1-007 is fixed and tested;
- F18A1-012 regression coverage exists;
- no approved fix weakens permission/approval/audit behavior;
- full Python suite passes;
- frontend tests/build remain green;
- npm high/critical audit remains 0;
- compileall passes;
- git diff --check passes;
- canonical status/gap/roadmap docs are updated;
- `docs/audits/PHASE_18A2_STABILIZATION.md` exists.

---

# 16. Final verdict format

End your response with exactly one of:

`STABILIZATION_PASS`

`STABILIZATION_PASS_WITH_DEFERRED_GAPS`

`STABILIZATION_BLOCKED`

Then include:

```text
Starting HEAD:
Ending HEAD:
Files changed:
Focused tests:
Full Python:
Frontend:
Security checks:
Findings closed:
Findings deferred:
Manual owner action required now:
May Computer Use V2 start:
Report:
```

For `May Computer Use V2 start`, use only:

- `YES`
- `NO`
- `YES_WITH_EXPLICIT_RESTRICTIONS`

Do not begin Computer Use V2 in the same task.
