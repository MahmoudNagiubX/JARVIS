# ACTIVE WORK PACKET — PHASE 18A BASELINE AUDIT & STABILIZATION

**Type:** replaceable execution packet, not a permanent architecture authority  
**Base to verify before work:** `main @ 54b67ba396ec45180f1b60ea472ef94c9ac181a9`

## Objective

Perform a senior-level, evidence-first audit of the current JARVIS repository before implementing Computer Use V2 or other new capability waves.

Do **not** redesign the system. Find and classify real gaps, fix only safe/proven defects, and preserve all locked authority/security boundaries.

## Mandatory context
Read:
1. `/AGENTS.md`
2. `docs/source_of_truth/00_JARVIS_START_HERE.md`
3. `docs/source_of_truth/01_JARVIS_CORE_SOURCE_OF_TRUTH.md`
4. `docs/source_of_truth/02_JARVIS_CURRENT_STATE.md`
5. `docs/source_of_truth/03_JARVIS_GAP_REGISTER.md`
6. `docs/source_of_truth/04_JARVIS_EXECUTION_ROADMAP.md`
7. `docs/source_of_truth/05_JARVIS_DECISION_LOG.md`
8. relevant `docs/architecture`, `docs/audits`, `docs/production`, `docs/deferred`, and tests.

## Hard constraints
- no second authority/service family;
- no broad rewrite;
- no new Phase 19 physical claim;
- no runtime cloud/AntiGravity/Google dependency;
- no secret/raw-media retention regression;
- no unrestricted shell/browser JavaScript/remote command;
- no migration from SQLite;
- no move of Core authority to VENOM;
- no fixing a test by weakening security semantics;
- no claiming a feature is live because an adapter seam exists.

## Pass 1 — repository baseline
Record exact:
- branch/HEAD/worktree state;
- Python/Node versions used by project tooling;
- focused Phase 13–17 tests where relevant;
- full Python suite;
- frontend tests/build;
- dependency audit;
- compile/static/whitespace checks documented by repo;
- skipped tests and why.

If current HEAD is no longer `54b67ba396ec45180f1b60ea472ef94c9ac181a9`, update the audit base and compare changes before continuing.

## Pass 2 — static debt scan
Search source/tests/config/docs for:
- `TODO`, `FIXME`, `HACK`, `TBD`, `XXX`, `pass`, `NotImplemented`, placeholder/deferred markers;
- broad exception handling and ignored errors;
- duplicated validation/policy/approval logic;
- direct adapter/controller/provider calls from model/worker/UI code;
- unused/dead compatibility adapters;
- false-success defaults;
- unbounded payload/context/retry/loop behavior;
- test-only/fake providers accidentally wired to normal runtime;
- hardcoded host/IP/path/credential assumptions;
- insecure temp files or secret logging;
- stale phase status in current docs.

Do not report ordinary words like “todo” in user message parsing or “hack” in malicious-test fixtures as engineering debt without context.

## Pass 3 — authority graph audit
Prove there is still one logical owner for:
- identity/device;
- permission/autonomy;
- approvals;
- audit;
- EventBus;
- BackgroundScheduler;
- AgentRuntime;
- Tool/Skill execution;
- Memory;
- World State;
- Goals/Missions;
- NotificationService;
- DeviceFabricService;
- VoiceCore.

Flag any bypass or duplicate as P0/P1.

## Pass 4 — security/data audit
Verify:
- external data remains untrusted;
- browser URL/redirect/SSRF defenses remain intact;
- MCP schema sanitization/bounds remain intact;
- path traversal/symlink boundaries are enforced;
- raw secrets/sensitive tool args are not durably persisted;
- raw audio/frames remain transient;
- approval resume is owner/device/transaction bound;
- consequential replay is prevented after restart;
- remote commands are typed/expiring/idempotent;
- not-configured integrations cannot report verified success.

## Pass 5 — representative end-to-end traces
Trace code and tests for:
1. safe local tool call;
2. approval-required tool call;
3. computer action;
4. browser read/research;
5. memory write/read/correction/delete;
6. mission approval + restart reconciliation;
7. automation/proactive notification;
8. node/home action in configured and not-configured states.

For each trace list the canonical service path and any bypass/gap.

## Pass 6 — documentation truth audit
Identify docs that are:
- current/canonical;
- current subsystem docs;
- historical snapshots;
- stale/contradictory.

The 2026-09-05 Master is archive/history; do not rewrite it to pretend it was always current.

## Finding format

For every real finding:

```text
Finding ID:
Gap ID: existing or new
Priority: P0/P1/P2/P3
Category: correctness/security/architecture/reliability/docs/performance/physical/config
Evidence: path + line/function/test/reproduction
Actual behavior:
Expected behavior:
Risk:
Canonical owner/service:
Locked decision affected: yes/no + DEC-ID
Recommended disposition: FIX_NOW / ROADMAP / NO_ACTION
Tests required:
Physical proof required: yes/no
```

## Allowed fixes during 18A
Fix immediately only when all are true:
- defect is objectively proven;
- intended behavior is already clear from existing locked decisions/tests;
- change is localized;
- no new authority/architecture is introduced;
- regression test can be added;
- full relevant verification remains green.

Otherwise add/update a Gap ID and stop at recommendation.

## Required final report

Return:
1. exact baseline and test results;
2. `P0/P1/P2/P3` finding table;
3. resolved false positives/no-action notes;
4. files changed and why;
5. tests added/changed;
6. full verification results;
7. updated Gap Register entries;
8. verdict: `AUDIT_GATE_PASS`, `AUDIT_GATE_PASS_WITH_ROADMAP_GAPS`, or `AUDIT_GATE_BLOCKED`;
9. whether Workstream A — Computer Use V2 may start.

No merge/push without the owner's normal explicit authorization workflow.
