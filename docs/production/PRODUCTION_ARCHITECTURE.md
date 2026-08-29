# JARVIS production architecture

The production runtime uses the authority architecture. The product spine
remains `EventBus -> AgentRuntime -> PermissionEngine -> ApprovalEngine
-> Audit -> Memory/WorldState/Goals -> Capabilities/Device/Experience`.

SQLite is the zero-install local adapter and remains the automated-test path.
`PostgresDatabase` is an injected production adapter boundary; it does not add
a driver or connect during import/bootstrap. Model access is provider-neutral,
with mock mode as the safe default and Ollama restricted to a loopback endpoint.

All mutation enters through identity/device authentication, permission, and
approval where required. The HTTP server binds only to loopback. The HUD is a
static shell; authenticated state, SSE, and the bounded authenticated
WebSocket stream are the data paths. Raw audio, raw frames, credentials, and
secrets are not retained in projections.

The runtime records process-owned transient runs and durable research ledgers.
On restart, transient core/research work is reconciled to `failed` with
`process_restarted`; no memories, conversations, goals, identities, or audit
records are deleted by recovery.

Live adapters are intentionally capability-gated. A missing PostgreSQL,
Ollama, Playwright, audio, satellite, engineering, Venom, home, or messaging
dependency is reported as unavailable/partial/deferred rather than replaced
with a false success.
