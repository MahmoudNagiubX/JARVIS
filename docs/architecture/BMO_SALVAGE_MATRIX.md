# BMO salvage matrix

This matrix identifies high-value BMO material for later migration. It is a
plan, not authorization to edit the historical BMO repositories. All source
repositories and owner-owned evidence remain read-only in Phase 01.

| BMO area | Value | Reuse mode | Boundary/handling notes |
|---|---|---|---|
| `identity/contracts.py` and `identity/service.py` | High | Adapt concepts and tests | Core identity authority; preserve strict validation, scope allowlist, device enrollment, rotation, heartbeat, and self-only reads |
| `identity/models.py` and repository | High | Later persistence adapter | Use only after schema ownership and migration review; no direct DB coupling in contracts |
| `model_gateway/contracts.py` | High | Adapt request/response/model identity types | Map to product `LLMRequest`/`LLMResponse`; preserve digest and health semantics |
| `model_gateway/gateway.py` and providers | High | Adapter implementation | Keep providers outside core; enforce local endpoint/model policy and circuit behavior |
| `tools/contracts.py` | High | Adapt risk/approval/audit fields | Canonical reference for tool authority; map into product `ToolContext` and result |
| `tools/service.py` | High | Migrate orchestration in slices | Keep permission, approval, idempotency, rate limits, budgets, reconciliation, and verification ordered |
| `tools/registry.py` | High | Adapter implementation | Registry is capability discovery, not authorization; authority remains separate |
| `tools/models.py` | Medium/high | Persistence adapter | Review data retention and argument redaction before reuse |
| `conversations/executor.py` | Medium/high | Runtime adapter | Add goal/session/event contracts; executor cannot become identity or approval owner |
| `satellites/windows` | High | Device adapter | Preserve capability binding, authentication, typed commands, loopback/tunnel assumptions, and evidence-driven deployment |
| `voice/state.py` and `voice/pipeline.py` | High | Voice adapter | Migrate state behavior and interruption; physical voice acceptance requires separate evidence |
| `db`, Alembic, reconciliation gates | Medium | Infrastructure reference | Introduce only with explicit persistence phase and integration tests |
| Phase 10 deployment scripts | Medium | Operations reference | Reuse operational lessons only; inspect enabled/active user service before repair; no blind Linger changes |
| `docs/phase_reports/evidence/PHASE_10_JARVIS_VOICE_CORE.json` | Protected | Never stage, overwrite, stash, commit, or delete | Owner-owned evidence is outside the Phase 01 target and must remain untouched |
| Phase 10 automated acceptance evidence | Protected | Never modify | Existing dirty evidence was recorded by Phase 00; preserve exactly |

## High-value salvage targets

1. Identity/device service and strict scoped contracts.
2. Model gateway and model identity/health validation.
3. Tool platform authority: risk, approval, audit, idempotency, and
   reconciliation.
4. Windows satellite capability protocol.
5. Voice state machine and pipeline boundaries.
6. Conversation executor, after it is subordinated to product goals/events.
