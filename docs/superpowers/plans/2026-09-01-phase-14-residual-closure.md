# Phase 14 residual closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the three residual Phase 14 UI contract gaps without changing the accepted local runtime architecture.

**Architecture:** Extend the existing read-only experience projection with safe notification fields from the canonical NotificationService. Replace the ChatScreen’s fixed polling deadline with explicit active-run state and bounded reconciliation that treats queued/running/resuming as non-terminal. Make the existing ApprovalCard await its parent decision callback so failed submits recover without weakening duplicate-submit protection.

**Tech Stack:** Python 3.11+, pytest, SQLite repository, React, TypeScript, Vite, Vitest, Testing Library, generated embedded UI assets.

**Spec:** `C:\Users\mahmo\Downloads\JARVIS_PHASE_14_FINAL_RESIDUAL_CLOSURE.md`

## Global Constraints

- Do not redesign Phase 14 or start Phase 15.
- Preserve the existing AgentRuntime, model authority, EventBus, scheduler, VoiceCore, notification authority, loopback HTTP, and embedded local asset boundary.
- Do not alter the local model, add cloud APIs/MCP, reopen physical voice, or redesign the whole UI.
- Backend state remains authoritative; queued, running, and resuming are active states.
- Full regression must remain at least 340 passing Python tests with no failures and at least 21 passing frontend tests with no failures.

---

### Task 1: Expose safe canonical notification projection fields

**Files:**
- Modify: `src/jarvis/contracts/experience.py` (`NotificationProjection`)
- Modify: `src/jarvis/bootstrap.py` (experience-state notification mapping)
- Test: `tests/test_phase_fourteen_residual_closure.py`

**Interfaces:**
- Consumes canonical `Notification` records returned by the existing `NotificationService.list(owner_id)`.
- Produces experience-state notification DTOs containing `source`, `created_at`, and a derived `important` boolean without exposing unrestricted metadata.

- [x] **Step 1: Write the failing integration test**

Add a test that inserts canonical notifications for proactive, system, and important cases, calls `CoreApplication.experience_state(owner_id)`, and asserts that the returned DTOs contain the source, ISO timestamp, and derived important flag. Assert that raw metadata fields are absent.

- [x] **Step 2: Run the focused test to verify it fails**

Run:

```powershell
python -m pytest -q tests/test_phase_fourteen_residual_closure.py -k notification
```

Expected: FAIL because the current projection omits `source`, `created_at`, and importance classification.

- [x] **Step 3: Implement the minimal projection extension**

Extend `NotificationProjection` with safe fields:

```python
source: str = "runtime"
created_at: datetime | None = None
important: bool = False
```

Map these from canonical notification records in `bootstrap.py`, deriving `important` from the canonical severity/category rather than copying unrestricted metadata.

- [x] **Step 4: Run the focused test to verify it passes**

Run:

```powershell
python -m pytest -q tests/test_phase_fourteen_residual_closure.py -k notification
```

Expected: PASS with all proactive, system, important, and timestamp assertions green.

### Task 2: Keep long-running chat active beyond 30 seconds

**Files:**
- Modify: `ui/src/screens/Screens.tsx` (`ChatScreen` active-run state and watcher)
- Test: `ui/src/screens/residual-closure.test.tsx`
- Regenerate: `src/jarvis/ui_static/app.js`

**Interfaces:**
- Consumes existing `POST /messages/start`, `GET /runs/{run_id}`, `POST /runs/{run_id}/cancel`, and conversation message endpoints.
- Produces explicit `{ runId, conversationId, state }` active-run state; only `succeeded`, `failed`, and `cancelled` clear it. `paused` remains visible as an approval state.

- [x] **Step 1: Write the failing frontend tests**

Add fake API tests that keep `GET /runs/run-long` in `running` for more than 30 seconds and assert that no timeout error is rendered, the Cancel button remains enabled, and a later `succeeded` response refreshes canonical messages and clears the active run.

- [x] **Step 2: Run the focused tests to verify the timeout bug**

Run:

```powershell
cd ui
npm.cmd test -- --run screens/residual-closure.test.tsx
```

Expected: FAIL because the current watcher stops after 150 attempts and reports `The local run did not reach a terminal state.`.

- [x] **Step 3: Implement bounded reconciliation without a false terminal state**

Replace the fixed 150-attempt failure path with an active-run watcher that reconciles state in bounded slices, keeps queued/running/resuming active, leaves paused visible, and never converts a watcher deadline into a backend failure. Preserve the existing cancel request and canonical message refresh paths.

- [x] **Step 4: Run the focused frontend tests to verify the fix**

Run:

```powershell
npm.cmd test -- --run screens/residual-closure.test.tsx
```

Expected: PASS for long-running state, cancellation availability, and eventual success cleanup/message refresh.

- [x] **Step 5: Regenerate and validate embedded assets**

Run from the repository root:

```powershell
python ui/build_frontend.py
```

Expected: three local JARVIS assets generated deterministically with no remote asset references.

### Task 3: Recover approval controls after a failed submit

**Files:**
- Modify: `ui/src/screens/Screens.tsx` (`ApprovalCard` and `ApprovalsScreen` callback contract)
- Test: `ui/src/screens/residual-closure.test.tsx`

**Interfaces:**
- Consumes the existing approval DTO with backend `run_id` and the current `api.post('/approvals/{id}', ...)` decision path.
- Produces a Promise-returning decision callback; the card disables controls while in flight, restores them on rejection, and continues to suppress duplicate submits.

- [x] **Step 1: Write the failing frontend test**

Make the approval POST reject, click Approve, assert the error is shown, then assert both Approve and Deny are actionable again and a second decision can be submitted.

- [x] **Step 2: Run the focused test to verify it fails**

Run:

```powershell
npm.cmd test -- --run screens/residual-closure.test.tsx
```

Expected: FAIL because `deciding` remains true after the rejected parent action.

- [x] **Step 3: Implement awaited failure recovery**

Change `onDecision` to return `Promise<void>`, await the parent action in the card, and reset `deciding` in `finally`. Keep the existing run-id guard and disabled state during the in-flight request.

- [x] **Step 4: Run the focused test to verify it passes**

Run:

```powershell
npm.cmd test -- --run screens/residual-closure.test.tsx
```

Expected: PASS with duplicate submit prevention and failed-submit recovery covered.

### Task 4: Run final residual closure gates and publish one commit

**Files:**
- Modify: `docs/audits/PHASE_14_FINAL_RESIDUAL_CLOSURE.md`

- [x] **Step 1: Run focused and regression suites**

Run the residual focused frontend/Python tests, the Phase 14 regression, the Phase 13 regression, and the full repository suite. Record actual counts and skips.

- [x] **Step 2: Run build and hygiene gates**

Run:

```powershell
cd ui; npm.cmd test -- --run; npm.cmd run build; npm.cmd audit --json
cd ..; python ui/build_frontend.py; python -m compileall src tests; git diff --check
```

- [x] **Step 3: Review scope and update the audit**

Confirm only one canonical implementation exists for EventBus, scheduler, VoiceCore, AgentRuntime, model gateway, and NotificationService. Confirm no broad SQL cleanup, remote assets, raw metadata, or architecture redesign entered the diff. Update `docs/audits/PHASE_14_FINAL_RESIDUAL_CLOSURE.md` with actual results.

- [x] **Step 4: Create exactly one commit and push**

Stage only the residual closure source, tests, generated assets, plan, and audit files, then run:

```powershell
git commit -m "fix: close phase 14 residual ui contracts"
git push origin main
```

- [x] **Step 5: Verify the remote handoff**

Run:

```powershell
git rev-parse HEAD
git rev-parse origin/main
git status --porcelain
```

Expected: the two revisions match and the worktree is clean.
