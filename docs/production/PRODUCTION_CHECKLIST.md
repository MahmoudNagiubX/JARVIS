# Production checklist

| Area | Status | Evidence / boundary |
|---|---|---|
| Regression baseline | PASS | Published base retained; current suite is reported by the remediation audit |
| Durable research ledger | PASS | SQLite ledger, restart reconciliation, acceptance tests |
| SQLite backup/restore | PASS | Online backup, integrity verification, explicit CLI |
| PostgreSQL | PARTIAL | Injected adapter and reconnect health; no local listener/client |
| pgvector | DEFERRED | No PostgreSQL deployment or extension available |
| Ollama/Qwen live | PARTIAL | Opt-in probe exists; no local Ollama/listener |
| Physical voice | DEFERRED | No physical voice session run; NoOp defaults |
| Windows satellite | PASS | Same-host process-separated Core/typed agent authority-path observation passed; second-host deployment not claimed; bounded evidence in `docs/phase09/evidence/PHYSICAL_COMPUTER_AUTHORITY_ACCEPTANCE.json` |
| Computer control | PARTIAL | Windows-safe/dry-run boundaries tested; no physical destructive actions |
| Browser/Playwright | PARTIAL | Deterministic controller tested; no Node/Playwright |
| Authenticated WebSocket | PARTIAL | Loopback handshake, auth, topic allowlist, bounded queue/lifetime; no full client-frame adapter |
| Jupyter/KiCad | DEFERRED | Adapter boundaries only |
| OCR/local vision | DEFERRED | No local capability available |
| Venom | DEFERRED | No valid local transport endpoint |
| Home Assistant/MQTT | DEFERRED | Restricted seam only; no listener |
| Email/Telegram/Discord | DEFERRED | No credentials; no real send |
| Startup/autostart | PARTIAL | Explicit lifecycle and host strategy; no task installed |
| Crash recovery | PASS | Core and research transient reconciliation |
| Security hardening | PASS | Loopback, scopes, limits, redaction, untrusted evidence |
| Performance profiling | PASS | Standard-library profiler and observability counters |

Paid runtime APIs: NONE. Models downloaded/copied: NONE. Donor repositories
modified: NONE. Legacy BMO repositories modified: NONE.

Before a live deployment, attach physical evidence for each deferred/partial
row and run the commands in the development acceptance documents.

Phase 10 desktop perception: native metadata/capture is on-demand,
owner/device/session-bound, raw-frame-free, and loopback-only. Metadata
awareness is disabled by default and must never enable pixel polling. Keep
OCR, vision, and camera deferred until an actual local capability is verified.
