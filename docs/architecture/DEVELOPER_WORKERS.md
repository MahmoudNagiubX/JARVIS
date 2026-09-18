# Developer workers

`DeveloperWorkerGateway` discovers the locally installed `codex` executable but
remains discovery-only unless `JARVIS_CODEX_WORKER_ENABLED=true` (or an
explicit adapter is injected). When enabled, it uses
`CodexDeveloperWorkerAdapter`. The adapter invokes
only `codex exec` with an explicit `read-only` sandbox, an exact resolved
workspace scope, an ephemeral session, bounded timeout/output, and a minimal
environment allowlist. It rejects missing scopes, oversized tasks, and tasks
that explicitly request credentials, cookies, tokens, private keys, or
environment files. Provider output is reduced to a small redacted summary;
raw JSONL, stderr, credentials, and file contents are not persisted.

The adapter has no write mode. Any future write-capable worker must resume only
after `WorkerCoordinator` consumes a canonical `ApprovalEngine` decision and
must retain the existing event, audit, and independent-verifier path. A local
Codex CLI being installed or opt-in being set is not live acceptance:
authentication, provider availability, and independent postcondition
verification remain deployment and owner gates. Google-account-backed CLI
candidates are excluded from discovery.

OpenClaw is a reserved adapter seam only. The local OpenClaw donor was audited
read-only; no gateway, channel, model, or tool code was copied and no direct
shell route was added. The core remains the single JARVIS authority.
