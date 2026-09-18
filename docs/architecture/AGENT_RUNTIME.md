# Agent runtime and workers

`AgentRuntime` owns the bounded text loop. It creates or validates the
owner-bound session and conversation, persists the user message and run, sends
requests through `ModelGateway`, executes only declared tools, pauses for
approval, persists the assistant response, and emits normalized events.

The default maximum is three model/tool steps and is capped at ten by
configuration. Runs can be resumed after an approval decision or cancelled;
the cancellation state is persisted and emitted. Client message ids provide a
small idempotency/replay boundary.

`LocalWorkerRuntime` provides typed worker requests and results for coding,
research, browser, computer, engineering, personal, automation, verifier, and
general-background categories. Handlers
are injected adapters with timeout and cancellation boundaries. The optional
Codex adapter is read-only and workspace-scoped; a missing CLI or unavailable
provider fails explicitly, and no write-capable external worker is required at
startup.
