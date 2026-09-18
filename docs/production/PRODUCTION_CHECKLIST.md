# Production checklist

| Area | Status | Evidence / boundary |
|---|---|---|
| Regression baseline | PASS | Published base retained; current suite is reported by the remediation audit |
| Durable research ledger | PASS | SQLite ledger, restart reconciliation, acceptance tests |
| SQLite backup/restore | PASS | Online backup, integrity verification, explicit CLI |
| PostgreSQL | PARTIAL | Injected adapter and reconnect health; no local listener/client |
| pgvector | DEFERRED | No PostgreSQL deployment or extension available |
| llama.cpp/Qwen local brain | PASS | Existing external GGUF loaded through one loopback llama.cpp server; text/provider-tool/three real AgentRuntime desktop turns/status tool/offline/restart PASS; bounded evidence in `docs/phase12/evidence/PHYSICAL_LOCAL_BRAIN.json` |
| Physical voice | PARTIAL | Explicit local wake/VAD/STT/TTS/playback runner and safe local smoke checks; human/operator acceptance remains open; `docs/phase13/evidence/PHYSICAL_LOCAL_VOICE.json` |
| Windows satellite | PASS | Same-host process-separated Core/typed agent authority-path observation passed; second-host deployment not claimed; bounded evidence in `docs/phase09/evidence/PHYSICAL_COMPUTER_AUTHORITY_ACCEPTANCE.json` |
| Computer control | PASS | Phase 11 grounded window, clipboard, and literal keyboard acceptance; bounded media-key volume; mute-state query remains explicitly unavailable |
| Installed desktop applications | PARTIAL | `InstalledApplicationRegistry` and native-first opaque-ref launch/focus path are implemented at `5a0ea52`; bounded discovery and deterministic tests pass, but the current physical Notepad probe is launch-only because foreground verification failed closed; no Tier A/B claim |
| Browser/Playwright | PARTIAL | Deterministic controller tested; no Node/Playwright |
| Authenticated WebSocket | PARTIAL | Loopback handshake, auth, topic allowlist, bounded queue/lifetime; no full client-frame adapter |
| Jupyter/KiCad | DEFERRED | Adapter boundaries only |
| OCR/local vision | DEFERRED | No local capability available |
| Venom | DEFERRED | No valid local transport endpoint |
| Home Assistant/MQTT | DEFERRED | Restricted seam only; no listener |
| Email/Telegram/Discord | DEFERRED | No credentials; no real send |
| Startup/autostart | PASS (automated) | Current-user reversible no-console startup registration is product-owned; physical login gate remains operator acceptance |
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

Phase 11 grounded desktop interaction: window actions are restricted to
minimize/maximize/restore over revalidated Phase 10 references; clipboard text
and keyboard arguments are bounded and ephemeral; keyboard execution rechecks
the foreground window for every chunk; mouse coordinates, arbitrary keys,
accessibility automation, and truthful mute-state control remain deferred.
Sanitized same-host physical evidence is in
`docs/phase11/evidence/PHYSICAL_DESKTOP_INTERACTION.json`.

## Final release closure checkpoint — 2026-09-18

The current feature branch remains `JARVIS_DESKTOP_RELEASE_CANDIDATE_PARTIAL`.
The closure run independently confirmed the public Browser V2 baseline with
the signed Brave executable and a dedicated JARVIS profile, current-schema
backup/restore integrity in an isolated temporary database, local security and
recovery regressions, the rendered local Command Center routes, and the
existing `RW-CALC-001` physical 3/3 evidence. It did not convert owner-session,
authenticated-service, physical-voice, or cold-shutdown gates into code PASS.

The hosted workflow is the authority for the final CI result; a local green
suite must not be substituted for hosted execution. Current service states are
truthfully `NOT_CONFIGURED` until the owner supplies exact destinations and
performs any required manual sign-in in the dedicated profile. ChatGPT web is
recorded separately as a service-surface block when it returns 403; an installed
OpenAI Codex package is not treated as ChatGPT.

Native desktop application setup is intentionally local and bounded. Set
`JARVIS_INSTALLED_APPS_CONFIG` only to the owner-approved local JSON settings
file (the default is `data/installed_apps.json`), refresh the catalog from the
authenticated Settings surface, and review the displayed support tier/login
status before using an app. The file stores only opaque disabled refs and
surface preferences. Do not persist executable paths, launch arguments,
cookies, credentials, or raw window identity. `AUTO` selects native desktop
for a verified launchable app; choosing `BROWSER` or `API` is only a surface
preference and does not configure that provider. Physical Tier A/B status still
requires a three-run foreground/postcondition receipt.
