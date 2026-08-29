# Master audit remediation

## Status

This document is the implementation record for the pre-Phase 08 remediation.
The canonical repository remains local-first and loopback-only. The change
preserves the existing phase commit history and adds one ordinary remediation
commit after validation.

| Finding | Status | Evidence in the repository |
|---|---|---|
| Worker combined exports | PASS | `agents/workers/__init__.py` exports runtime and coordination symbols together; regression test covers both. |
| Skill risk and approval propagation | PASS | `skills/policy.py` computes the most restrictive manifest/step/tool risk and fails closed for unknown risk. |
| Durable skill execution/resume | PASS | `skill_executions` persistence, execution id, current step, approval id, correlation id, bounded results, and idempotent resume. |
| Direct skill authority | PASS | Direct handlers pass through `SkillPolicy`, explicit permission actions, audit, and bounded backup scope. |
| Mission approval fail-closed | PASS | Missing approval engine cannot create a resumable wait; resume validates owner, mission, step, and durable approval. |
| Automation approval state | PASS | Automation runs preserve awaiting-approval state and child execution references. |
| Mission automation | PASS | Mission actions create and plan a bounded mission with a persisted child mission id. |
| Automation execution principal | PASS | `AutomationExecutionBinding` stores owner, identity, device/local service, scopes, capabilities, creator, and enabled state; fresh resolution rejects revoked/offline bindings. |
| Private GET authentication | PASS | Private resource and metadata GET routes require an authenticated principal; only health and static HUD shells remain unauthenticated. |
| Stream credentials | PASS | `POST /v1/auth/stream-ticket` issues opaque short-lived one-use tickets; SSE/WebSocket streams accept ticket or normal Bearer authentication, never a long-lived query credential. |
| Approval owner binding | PASS | Approval reads compare the durable requester owner with the authenticated owner. |
| Tool schemas | PASS | Registry-owned JSON schemas are supplied to the model and validated at the tool boundary. |
| Memory extraction | PASS | Deterministic, optional existing-ModelGateway local, and composite extractors use strict bounded parsing and preserve MemoryPolicy rejection. |
| Adaptive personalization | PASS | Inspectable preferred tools, roots, workflows, periods, notification, briefing, worker, and response-length preferences are editable and bounded. |
| Capability truth | PASS | Capability consistency reporting exposes provider, availability, risk, environment requirements, and reason metadata. |
| Packaging/docs | PASS | Package metadata is honest for private development; stale current Phase 03/04/05 wording was removed from active README, architecture, testing, and production docs. |

## Security acceptance

- Missing-auth private GET: 401.
- Query credential on a private GET: rejected; Bearer headers are required.
- Wrong requested owner: rejected after principal authentication.
- Invalid/revoked device or identity: rejected.
- Approval and event endpoints: authenticated and owner-filtered.
- Expired, wrong-scope, wrong-device, and reused stream tickets: rejected.
- No public bind, shell backup execution, raw media retention, or model
  download/copy was introduced.

## Validation and live boundary

The required standard-library unittest suite remains at or above the 42-test
baseline: the final local run passed 58 tests, including the 16 focused
remediation tests in `tests/test_master_audit_remediation.py`. The remediation
commit hash is recorded in the completion handoff after publication.

## Independent GitHub review follow-up

Base reviewed: `b36a8989cc1e42fb2b6ed27d0892e63ece720f01`.

- Automation bindings now resolve to the intersection of the captured and
  currently active device scopes/capabilities. Authority can only increase
  through the explicit `reauthorize_binding` path; revocation fails closed.
- Offline handling is action-level through `OfflineModeService`: local
  notifications, briefings, missions, and local skills continue; skills with
  remote/cloud capabilities or network requirements are suppressed.
- `CoreHttpServer.PUBLIC_GET_ROUTES` is exactly `/health`, `/hud`, and
  `/experience/hud`. All other GETs authenticate Bearer/device/identity
  headers; capability listings are bound to the authenticated device.
- Stream tickets remain opaque, short-lived, one-use, and reject a revoked
  device at consumption time. `MissionService(..., approvals=None)` fails
  with `approval_engine_unavailable`, never a null-id approval wait.
- The legacy memory extraction entry point now delegates to
  `DeterministicMemoryExtractor.extract_sync`; no duplicate deterministic
  regex implementation remains. Execution-level skill event correlation is
  deferred because registry lifecycle events are intentionally skill-wide.

The independent-review test additions raise the focused suite to 22 tests;
the final local regression run passed 64 tests. The published commit hash is
recorded in the completion handoff without rewriting history.

Physical voice acceptance, real satellite transport, Playwright, PostgreSQL
client/listener, Ollama availability, OCR/local vision, Venom transport, and
external messaging remain live/deployment evidence debt. They are not claimed
as completed by this local remediation.
