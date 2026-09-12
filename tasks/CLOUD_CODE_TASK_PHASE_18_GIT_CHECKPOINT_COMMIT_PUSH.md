# CLOUD CODE TASK — PHASE 18 CHECKPOINT COMMIT + PUSH

**Project:** JARVIS  
**Target agent:** Cloud Code  
**Task mode:** Verification + clean checkpoint commits + push  
**Owner:** Mahmoud  
**Date:** 2026-09-12

---

# 0. Mission

You are starting with zero prior session knowledge.

The current local worktree contains already-completed and already-tested work from:

1. Phase 18A.1 baseline audit
2. Phase 18A.2 targeted stabilization
3. Phase 18 Workstream A.1 UIA backend evaluation

The owner has now changed the Git workflow:

> From this point forward, implementation work that passes its required verification must be committed and pushed so each checkpoint can be independently reviewed from GitHub before the next implementation slice continues.

Your job in this task is **not to implement new features**.

Your job is to:

1. verify the current local state;
2. ensure the existing changes match the completed audit/stabilization/A1 reports;
3. create a dedicated Phase 18 feature branch;
4. run the required verification;
5. create clean, logically separated commits;
6. push the branch to `origin`;
7. return exact branch and commit SHAs for independent GitHub review.

Do not merge to `main`.

Do not start Workstream A2.

---

# 1. Mandatory bootstrap

Find the real repository root:

```powershell
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git status --short
git remote -v
```

Expected repository:

`C:\Jarivs\00_final\jarvis`

Expected starting HEAD:

`54b67ba396ec45180f1b60ea472ef94c9ac181a9`

The current branch may still be `main`.

Read:

1. `AGENTS.md`
2. `docs/source_of_truth/00_JARVIS_START_HERE.md`
3. `docs/source_of_truth/01_JARVIS_CORE_SOURCE_OF_TRUTH.md`
4. `docs/source_of_truth/02_JARVIS_CURRENT_STATE.md`
5. `docs/source_of_truth/03_JARVIS_GAP_REGISTER.md`
6. `docs/source_of_truth/04_JARVIS_EXECUTION_ROADMAP.md`
7. `docs/source_of_truth/05_JARVIS_DECISION_LOG.md`
8. `docs/audits/PHASE_18A1_BASELINE_AUDIT.md`
9. `docs/audits/PHASE_18A2_STABILIZATION.md`
10. `docs/audits/PHASE_18_WORKSTREAM_A1_UIA_BACKEND_EVALUATION.md`

---

# 2. Git policy from now on

Use this branch for Phase 18 Computer Use work:

`feature/phase-18-computer-use-v2`

Rules:

- never push implementation commits directly to `main`;
- never merge into `main` during this task;
- never force-push;
- never rewrite history;
- never discard owner changes;
- every future implementation slice should produce one or more focused commits only after tests pass;
- each pushed commit must be independently reviewable;
- use explicit `git add <paths>` rather than `git add .`;
- do not commit unrelated local files.

If the branch already exists locally or remotely, verify exactly what it points to before using it.

If it does not exist, create it from the current validated baseline while preserving the current worktree:

```powershell
git switch -c feature/phase-18-computer-use-v2
```

Do not create it from an unexpected SHA.

---

# 3. Expected current changes

The completed Phase 18A.2 report says the stabilization work changed:

Production:
- `src/jarvis/agents/runtime/runtime.py`
- `src/jarvis/computer/service.py`
- `src/jarvis/devices/fabric.py`
- `src/jarvis/devices/home/service.py`
- `src/jarvis/tools/service.py`

Tests:
- `tests/test_phase_eighteen_stabilization.py`

Canonical bootstrap/source of truth:
- `AGENTS.md`
- `docs/source_of_truth/00_JARVIS_START_HERE.md`
- `docs/source_of_truth/01_JARVIS_CORE_SOURCE_OF_TRUTH.md`
- `docs/source_of_truth/02_JARVIS_CURRENT_STATE.md`
- `docs/source_of_truth/03_JARVIS_GAP_REGISTER.md`
- `docs/source_of_truth/04_JARVIS_EXECUTION_ROADMAP.md`
- `docs/source_of_truth/05_JARVIS_DECISION_LOG.md`
- `docs/source_of_truth/06_ACTIVE_WORK_PACKET_PHASE_18A.md`

Audit/task history expected:
- `docs/audits/PHASE_18A1_BASELINE_AUDIT.md`
- `docs/audits/PHASE_18A2_STABILIZATION.md`
- `tasks/CLOUD_CODE_TASK_PHASE_18A1_BASELINE_AUDIT.md`
- `tasks/CLOUD_CODE_TASK_PHASE_18A2_STABILIZATION_FIXES.md`

A1 evaluation expected:
- `docs/audits/PHASE_18_WORKSTREAM_A1_UIA_BACKEND_EVALUATION.md`
- `tasks/CLOUD_CODE_TASK_PHASE_18_WORKSTREAM_A1_UIA_BACKEND_EVALUATION.md` if present

Before staging anything:

```powershell
git status --short
git diff -- src tests
git diff -- docs/source_of_truth
```

Compare the implementation with the Phase 18A.2 report.

If there are unexpected tracked modifications outside the completed work, STOP and report them.

If there are unrelated untracked owner files, leave them untouched and do not stage them.

---

# 4. Verification before any commit

Re-run the green gate.

## Python

```powershell
python -m pytest tests -q
python -m compileall src tests -q
git diff --check
```

Expected approximate baseline after Phase 18A.2:

- 530 total Python tests, subject only to the already-documented environment-dependent active-window pass/skip variation;
- 36 subtests;
- compileall pass;
- diff check pass.

A 529 passed / 1 known justified skip result is acceptable only if it is the same already-documented active-window condition.

Any new failure is blocking.

## Frontend

Run:

```powershell
cd ui
npm test
npm run build
npm audit --audit-level=high
cd ..
```

Expected:

- Vitest: 75 passed
- build: clean
- high/critical vulnerabilities: 0

Do not commit if these gates fail unexpectedly.

---

# 5. Commit structure

Create **two separate commits**.

Do not squash them together.

## Commit 1 — validated stabilization baseline

Recommended message:

`fix: close phase 18 stabilization gate`

Stage only the files belonging to Phase 18A.1 / Phase 18A.2 and the canonical bootstrap.

At minimum:

```text
AGENTS.md
docs/source_of_truth/
docs/audits/PHASE_18A1_BASELINE_AUDIT.md
docs/audits/PHASE_18A2_STABILIZATION.md
tasks/CLOUD_CODE_TASK_PHASE_18A1_BASELINE_AUDIT.md
tasks/CLOUD_CODE_TASK_PHASE_18A2_STABILIZATION_FIXES.md
src/jarvis/agents/runtime/runtime.py
src/jarvis/computer/service.py
src/jarvis/devices/fabric.py
src/jarvis/devices/home/service.py
src/jarvis/tools/service.py
tests/test_phase_eighteen_stabilization.py
```

Before committing:

```powershell
git diff --cached --stat
git diff --cached --check
```

Inspect the cached diff for:
- no secret/token;
- no accidental owner file;
- no unrelated change;
- no generated binaries;
- no environment/venv files.

Then commit.

Record the exact SHA:

```powershell
git rev-parse HEAD
```

---

## Commit 2 — UIA backend evaluation evidence

Recommended message:

`docs: record phase 18 UIA backend evaluation`

Stage only:

```text
docs/audits/PHASE_18_WORKSTREAM_A1_UIA_BACKEND_EVALUATION.md
tasks/CLOUD_CODE_TASK_PHASE_18_WORKSTREAM_A1_UIA_BACKEND_EVALUATION.md
```

If the task file does not exist in the repository, do not fabricate it; commit only the report and state that clearly.

Do **not** update `05_JARVIS_DECISION_LOG.md` in this checkpoint solely to lock the backend recommendation. A1 produced a recommendation, not an owner-approved architecture lock.

Before committing:

```powershell
git diff --cached --stat
git diff --cached --check
```

Then commit and record the exact SHA.

---

# 6. Post-commit verification

After both commits:

```powershell
git status --short
git log --oneline --decorate -5
git diff main...HEAD --stat
```

The only remaining local files, if any, must be explicitly identified and must not be silently staged.

The repository must not contain accidental secrets.

Do not amend either commit merely to make the history prettier after recording its SHA unless a genuine mistake is found before push.

---

# 7. Push

Push only the feature branch:

```powershell
git push -u origin feature/phase-18-computer-use-v2
```

Do not push to `main`.

Do not force-push.

If authentication fails:
- do not retry with unsafe credential handling;
- report a manual GitHub authentication gate.

After push, verify:

```powershell
git status -sb
git log --oneline --decorate -5
```

If available, confirm the branch's upstream points to:

`origin/feature/phase-18-computer-use-v2`

---

# 8. No implementation in this task

Forbidden:

- Workstream A2 code;
- adding `uiautomation` to `pyproject.toml`;
- changing the backend decision;
- mouse/keyboard automation;
- file-access expansion;
- unrelated cleanup;
- dependency upgrade;
- merge to main;
- PR merge.

This is only a verified Git checkpoint.

---

# 9. New permanent workflow rule

Record this in the task report only; do not invent a new architecture decision.

For all future implementation tasks:

1. read repo-local Source of Truth;
2. inspect current branch/HEAD;
3. implement only approved scope;
4. run focused tests;
5. run required full regression gates;
6. inspect diff;
7. commit only if green;
8. push the feature branch;
9. return commit SHA(s);
10. stop;
11. independent planner/reviewer inspects GitHub commit diff before next implementation slice or merge.

Documentation-only spikes may also be committed/pushed if they are intended as durable project evidence.

No automatic merge to `main`.

---

# 10. Required checkpoint report

Create:

`docs/audits/PHASE_18_GIT_CHECKPOINT.md`

Include:

- starting branch/HEAD;
- verification results;
- branch created/used;
- Commit 1 SHA/message/files;
- Commit 2 SHA/message/files;
- final worktree status;
- remote push result;
- any untracked files left intentionally;
- confirmation no merge to main occurred;
- confirmation no secrets were committed;
- exact next review gate: independent GitHub commit review before A2.

If creation of this report would itself create an uncommitted file after the two required commits, include it in **Commit 2** before that commit is finalized.

---

# 11. Final response format

Return:

`CHECKPOINT_PUSH_PASS`

or:

`CHECKPOINT_PUSH_BLOCKED`

Then:

```text
Branch:
Starting HEAD:
Verification:
Commit 1:
Commit 1 message:
Commit 2:
Commit 2 message:
Push:
Remote branch:
Final worktree:
Untracked files left:
Main modified remotely:
Manual owner action required:
Next gate:
Report:
```

For `Main modified remotely`, the expected answer is:

`NO`

For `Next gate`, the expected answer is:

`INDEPENDENT_GITHUB_COMMIT_REVIEW_BEFORE_A2`
