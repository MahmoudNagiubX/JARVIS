# Mega Phase 02 migration backlog

Recommended next execution: **MEGA PHASE 02 — Core Runtime Migration &
Integration**.

## Work packages

1. **Runtime/event integration**
   - Add durable correlation/session identifiers to the runtime context.
   - Introduce event persistence/outbox only after the in-memory semantics are
     covered by tests.
   - Define conversation, agent, worker, and tool event schemas on the Phase 01
     envelope.
2. **BMO authority adapter**
   - Map the BMO identity service into `IdentityService`.
   - Map permission, approval, audit, and tool records into their contracts.
   - Preserve strict validation and fail-closed behavior.
3. **Model gateway adapter**
   - Implement a local-only provider adapter with digest/model allowlisting.
   - Add health, timeout, cancellation, and provider contract tests.
   - Do not download or duplicate existing model artifacts.
4. **Conversation and agent runtime**
   - Migrate BMO conversation execution behind goals and events.
   - Select narrow PersonalJarvis mission/worker patterns and aceFelix
     orchestration/recovery patterns.
   - Keep workers isolated and make all tool proposals pass common authority.
5. **Tool platform**
   - Adapt BMO catalog, idempotency, risk, rate, budget, sandbox, approval,
     verification, and reconciliation behavior.
   - Add read-only, reversible, consequential, and forbidden tool fixtures.
6. **Memory and world state**
   - Adapt PersonalJarvis memory/wiki behavior behind owner-scoped records.
   - Add explicit observation provenance, confidence, retention, and audit
     rules; never hide state inside a manager singleton.
7. **Voice and devices**
   - Adapt BMO voice state/pipeline and Windows satellite contracts.
   - Add aceFelix duplex/VAD/barge-in only behind `RealtimeVoiceSession`.
   - Test interruption and authorization separately from physical audio claims.
8. **Browser/computer controllers**
   - Add typed controller adapters with device binding and evidence-bearing
     results.
   - Keep browser isolation and computer-use approval policies explicit.
9. **Engineering validation**
   - Run stdlib/unit tests offline first, then narrowly scoped integration tests.
   - Add static import-boundary checks, mypy/ruff configuration, and migration
     evidence.
   - Re-check donor/BMO Git status and protected evidence before handoff.

## Phase 02 exit criteria

Phase 02 is complete only when one real end-to-end, low-risk capability can
flow through identity, permission, tool validation, audit, execution,
verification, and correlated events without importing donor internals into the
core. High-risk actions, public bindings, model downloads, and broad voice
acceptance remain separate decisions.
