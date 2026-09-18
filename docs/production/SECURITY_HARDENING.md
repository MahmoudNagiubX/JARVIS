# Security hardening

- Bind the core API to `127.0.0.1`/`::1` only; there is no permissive CORS.
- Authenticate data and mutation routes with credential, device, and identity
  binding. Capability checks, permission, approval, audit, and idempotency
  remain in the authority plane.
- Keep request bodies bounded, client topics allowlisted, client sessions
  capped, and WebSocket queues bounded. Backpressure emits a control error;
  it does not grow memory without limit.
- Treat research pages/documents as untrusted evidence. Page instructions are
  never executed and raw perception/audio is not persisted by the core.
- Use the shared redaction rules for credentials, tokens, passwords, cookies,
  raw audio, raw frames, and authorization values. Never log a raw credential.
- Developer workers use the optional bounded Codex adapter only when the local
  CLI is present. It is read-only, workspace-scoped, ephemeral, output-bounded,
  and environment-allowlisted; there is no arbitrary shell route, write mode,
  public endpoint, paid API, or model download in the default runtime. A live
  worker result still requires the existing independent verifier before it is
  treated as verified.

Known operational debt: query-string authentication is retained for the
existing SSE/HUD client compatibility path, so reverse-proxy/access logging
must be configured not to retain URLs containing credentials. A future
transport migration should prefer short-lived headers/cookies.
