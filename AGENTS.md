# JARVIS — AGENT OPERATING CONTRACT

**Status:** CANONICAL AGENT BOOTSTRAP  
**Snapshot reviewed:** 2026-09-12  
**Repository:** `MahmoudNagiubX/JARVIS`  
**Reviewed `main` HEAD:** `54b67ba396ec45180f1b60ea472ef94c9ac181a9` — `fix: close phase 17 real network readiness`

> This file tells every coding/review agent how to work on JARVIS. It is intentionally short enough to read before every task. It is not the architecture document and must not become a second roadmap.

## 1. Mandatory read order

Before changing code, read in this order:

1. `AGENTS.md`
2. `docs/source_of_truth/00_JARVIS_START_HERE.md`
3. `docs/source_of_truth/01_JARVIS_CORE_SOURCE_OF_TRUTH.md`
4. `docs/source_of_truth/02_JARVIS_CURRENT_STATE.md`
5. `docs/source_of_truth/03_JARVIS_GAP_REGISTER.md`
6. `docs/source_of_truth/04_JARVIS_EXECUTION_ROADMAP.md`
7. `docs/source_of_truth/05_JARVIS_DECISION_LOG.md`
8. Only then read the architecture docs/tests relevant to the requested subsystem.

For implementation truth, always inspect current Git HEAD and tests. Never assume this snapshot is still HEAD.

## 2. Truth hierarchy

Use different sources for different kinds of truth:

- **Implementation truth:** current repository code + current tests + current audit evidence at the exact HEAD.
- **Architecture/product truth:** `01_JARVIS_CORE_SOURCE_OF_TRUTH.md` + accepted decisions in `05_JARVIS_DECISION_LOG.md`.
- **Current status:** `02_JARVIS_CURRENT_STATE.md`.
- **Open work:** `03_JARVIS_GAP_REGISTER.md` + `04_JARVIS_EXECUTION_ROADMAP.md`.
- **Historical rationale only:** the ultra-complete 2026-09-05 Master archive and old phase plans/reports.

A historical file must not silently override a newer accepted decision or current code evidence.

## 3. Core engineering rule

**Extend the existing authority; do not create a second authority.**

Do not duplicate or bypass:
- `AgentRuntime`
- identity/device authority
- `PermissionEngine`
- `ApprovalEngine`
- audit authority
- `ToolRegistry` / `ToolExecutionService`
- `ComputerActionService`
- `BrowserActionService`
- Memory authority
- World State authority
- Goal/Mission authority
- `BackgroundScheduler`
- EventBus
- `NotificationService`
- `DeviceFabricService`
- `VoiceCore`

Prefer a new adapter/provider behind an existing typed boundary over a new top-level subsystem.

## 4. Canonical action path

Every real side effect must preserve this shape:

```text
request/event
→ authenticated owner/device/session
→ AgentRuntime / mission context
→ capability selection
→ permission + autonomy/risk evaluation
→ approval when required
→ canonical typed service
→ adapter/provider
→ real execution
→ independent verification
→ audit/event/result
```

No specialist agent, MCP server, browser page, model, UI, plugin, script, device, or external worker may bypass this path.

## 5. Closed-loop execution rule

For computer/browser/device actions use:

```text
OBSERVE → GROUND → PLAN → POLICY → ACT ONE BOUNDED STEP
→ VERIFY → RECOVER/REPLAN IF NEEDED → AUDIT/RECEIPT
```

Never report success from intent, a click, a returned HTTP 200, or a mock alone. Verify the actual target state when the capability permits it.

## 6. Security invariants

- Local-first, free-runtime, offline-capable.
- One logical authority, one owner.
- External/browser/research/MCP/document content is untrusted data, never authority.
- The LLM cannot grant itself permissions or approvals.
- No unrestricted shell as a main-agent capability.
- No arbitrary remote shell commands in the device fabric.
- No raw secrets in Memory, logs, audit, prompts, approvals, UI projections, or source control.
- Raw mic audio, raw screenshots/frames, raw camera streams, cookies, tokens, passwords, private keys, and sensitive tool arguments are transient by default.
- Voice cannot silently approve high-risk actions.
- Fail closed on ambiguous identity, target, permission, or verification state.
- Physical PASS requires physical evidence. Tests/mocks are not physical evidence.

## 7. Change discipline

Before coding:
1. confirm current branch and HEAD;
2. identify the open Gap ID / roadmap workstream;
3. inspect relevant code, tests, architecture docs, and prior audit;
4. state whether a locked decision is affected;
5. avoid broad refactors unless evidence proves they are required.

During coding:
- keep changes scoped;
- reuse canonical services;
- keep outputs bounded;
- add/adjust tests for behavior and security;
- preserve truthful degraded states;
- do not introduce hidden cloud/runtime dependencies.

Before claiming completion:
- run focused tests;
- run required regressions;
- verify build/static checks relevant to the change;
- inspect diff for authority bypasses, secrets, dead compatibility code, and stale docs;
- update `02`, `03`, `04`, or `05` only if project truth actually changed.

## 8. Documentation ownership

Each canonical file has one responsibility:

| File | Owns |
|---|---|
| `00_JARVIS_START_HERE.md` | bootstrap/read order/product summary |
| `01_JARVIS_CORE_SOURCE_OF_TRUTH.md` | locked architecture and safety invariants |
| `02_JARVIS_CURRENT_STATE.md` | what is actually implemented/partial/not configured |
| `03_JARVIS_GAP_REGISTER.md` | open gaps + resolved historical gaps |
| `04_JARVIS_EXECUTION_ROADMAP.md` | execution order and exit gates |
| `05_JARVIS_DECISION_LOG.md` | accepted/superseded/decision-needed choices |

Do not duplicate large sections across files. Link to the owning file instead.

## 9. Status vocabulary

Use only these meanings:
- `IMPLEMENTED` — code exists and is covered by current evidence/tests.
- `PARTIAL` — meaningful implementation exists but the desired capability is incomplete.
- `NOT_CONFIGURED` — implementation seam exists but no live provider/deployment is configured.
- `PLANNED` — accepted target, not implemented yet.
- `BLOCKED` — cannot proceed until a named dependency/evidence condition is resolved.
- `PHYSICAL_PENDING` — code may pass, but real hardware/human acceptance is not proven.
- `RESOLVED` — historical gap closed by current evidence; do not reopen without regression evidence.

## 10. Forbidden shortcuts

Do not:
- create `AgentRuntimeV2`, `SecondVoiceCore`, `BrowserAgentV2`, `RoomBrain`, `HomeBrain`, or equivalent duplicate authority;
- move Core authority to VENOM;
- migrate SQLite to PostgreSQL without an approved decision;
- make PyAutoGUI the primary computer-control architecture;
- make Selenium the primary browser architecture;
- expose unrestricted JavaScript/shell through browser control;
- let web text or MCP schema become system instructions;
- turn every discovered MCP tool into model context;
- add a second scheduler for automations;
- make UI state authoritative;
- claim a feature is live because a class/interface exists;
- claim physical success from fake servers, fixtures, or unit tests;
- silently change locked architecture while “cleaning up.”

## 11. Active work

The immediate work gate is **Phase 18A — Baseline Audit & Stabilization**, defined in `04_JARVIS_EXECUTION_ROADMAP.md` and tracked in `03_JARVIS_GAP_REGISTER.md`.

No new capability wave should be merged before that gate produces a reviewed baseline and gap report.
