# JARVIS — START HERE

**Status:** CANONICAL BOOTSTRAP  
**Reviewed:** 2026-09-12  
**Repository:** `MahmoudNagiubX/JARVIS`  
**Reviewed HEAD:** `54b67ba396ec45180f1b60ea472ef94c9ac181a9`

## 1. What JARVIS is

JARVIS is Mahmoud's persistent, single-owner, local-first Personal AI Operating System inspired by the useful capability/UX of Tony Stark's J.A.R.V.I.S., not a literal Marvel copy.

The target experience is one coherent assistant presence that can:
- understand Egyptian Arabic first, English second, and mixed technical language;
- run a local LLM and remain useful offline;
- remember approved personal knowledge while keeping fresh World State separate;
- understand desktop context and safely control Windows applications;
- automate the browser and extract/research web information;
- work with files/projects and developer tools;
- manage goals, missions, tasks, reminders, routines, and proactive notifications;
- use specialist workers behind one assistant identity;
- communicate through configured services such as email/calendar when adapters are added;
- control approved Home Assistant/MQTT/ESP32 devices;
- continue across NIGHTFURY, VENOM, room endpoints, and future devices;
- support natural voice, follow-up, interruption, and eventually multi-room presence;
- show real progress/state in the Command Center;
- ask approval for consequential actions and keep an audit trail;
- start with minimal manual setup and degrade truthfully when something is unavailable.

## 2. Current architecture in one sentence

> JARVIS is a single-authority, local-first personal AI OS where a bounded orchestrator retrieves only relevant context, delegates to least-privileged specialists, executes through typed capability services using deterministic/semantic control before visual fallbacks, verifies real actions in a closed loop, and persists only approved provenance-aware state under explicit security and audit rules.

## 3. Read order for a new chat or coding agent

```text
AGENTS.md
→ 00_JARVIS_START_HERE.md
→ 01_JARVIS_CORE_SOURCE_OF_TRUTH.md
→ 02_JARVIS_CURRENT_STATE.md
→ 03_JARVIS_GAP_REGISTER.md
→ 04_JARVIS_EXECUTION_ROADMAP.md
→ 05_JARVIS_DECISION_LOG.md
→ relevant repo architecture/audit/tests
```

Do not read the 2 MB historical Master archive by default. Read it only when historical rationale, an old decision, or an old phase detail is needed.

## 4. Source-of-truth split

### Implementation truth
Inspect the actual current repository and exact commit. The snapshot in these files is not a substitute for reading newer code.

### Product/architecture truth
Use `01_JARVIS_CORE_SOURCE_OF_TRUTH.md` and accepted decisions in `05_JARVIS_DECISION_LOG.md`.

### Status truth
Use `02_JARVIS_CURRENT_STATE.md`.

### Work truth
Use `03_JARVIS_GAP_REGISTER.md` and `04_JARVIS_EXECUTION_ROADMAP.md`.

### Historical truth
Use `JARVIS_ULTRA_COMPLETE_MASTER_DEVELOPMENT_CONTEXT_2026-09-05.md` and old phase/audit documents only as historical evidence.

## 5. Current snapshot that matters

Current reviewed `main`:

```text
54b67ba396ec45180f1b60ea472ef94c9ac181a9
fix: close phase 17 real network readiness
```

At this commit the Phase 17 audit records:
- Phase 17 focused: 79 passed;
- Phase 13–16 regression: 218 passed + 11 subtests;
- full Python suite: 514 passed, 1 justified skip, 36 subtests;
- frontend Vitest: 75 passed;
- frontend build: clean;
- npm high-severity audit: 0 vulnerabilities;
- compileall and diff checks: pass.

This supersedes the 2026-09-05 Master snapshot that still marked Phase 17 network closure as HOLD.

## 6. Official phase position

Historical Mega Phase numbering remains unchanged:

```text
Phase 01–12   closed in repository history
Phase 13      code/product pass; full physical voice pending
Phase 14      final pass
Phase 15      final pass
Phase 16      final pass
Phase 17      code/architecture + network-readiness closure pass at current HEAD;
              physical VENOM/Home/ESP32/room gates remain pending
Phase 18      not yet executed as the new stabilization/enhancement program
Phase 19      final physical end-to-end acceptance/release remains pending
```

Do not invent Phase 20+ merely to organize work. Use workstreams/waves inside Phase 18 and physical gates inside Phase 19.

## 7. Immediate next action

Before implementing new features, run **Phase 18A — Baseline Audit & Stabilization Gate**:
- establish a clean current baseline;
- run current tests/build/security checks;
- inspect TODO/FIXME/HACK/dead/duplicate/deferred paths;
- find authority/policy/approval/audit bypasses;
- compare code to the locked core flow;
- identify stale/conflicting docs;
- classify every finding in the Gap Register;
- fix only proven low-risk defects during the audit; route architecture changes for review.

After the audit gate, the first capability workstream is **Computer Use V2**.

## 8. Owner inputs still expected

These inputs extend capabilities without rewriting the core:
- screenshots/images showing desired JARVIS capabilities and UX;
- manually curated personal information for the Personal Knowledge Vault;
- priority desktop applications/workflows;
- priority browser workflows;
- exact physical deployment state when VENOM/Home work resumes.

Map each new requested feature as:

```text
Capability → owning specialist → canonical service/tool → permissions/risk
→ required data → verification → tests/evidence → roadmap priority
```

## 9. Historical archive rule

The large Master context remains valuable, but it contains superseded states such as the pre-`54b67ba` Phase 17 HOLD and much older BMO/VENOM architectures. Never let historical topology silently override current accepted architecture.
