# JARVIS desktop product lifecycle

The installed Windows product is an orchestration shell around the existing
JARVIS runtime. `JarvisDesktopLifecycle` owns startup order, user-scoped
configuration, secure local credential restoration, device reconciliation,
HUD hosting, tray state, and shutdown. It does not create a second
`IdentityService`, `VoiceCore`, `AgentRuntime`, `ModelGateway`, `ToolRegistry`,
`EventBus`, scheduler, or model server.

## Startup

```text
single-instance lock
  -> versioned safe settings
  -> current-user credential restore
  -> IdentityService authentication
  -> existing Core runtime
  -> existing LlamaCppRuntimeSupervisor / model health
  -> local voice asset validation
  -> stable audio selector reconciliation
  -> existing VoiceCore / LocalVoiceRuntime
  -> existing authenticated HUD and tray
```

An empty store enters `SETUP_REQUIRED`; background startup never silently
creates an owner. Explicit first-run setup reuses the sole active owner and
identity, or uses the existing enrollment service to create one product-owned
local desktop device. The raw credential is held only by Windows Credential
Manager (DPAPI CurrentUser fallback) and is never placed in settings, SQLite,
logs, startup arguments, or the HUD.

## Safe local state

Settings live at `%LOCALAPPDATA%\JARVIS\config\settings.json` and contain only
versioned non-secret selectors, thresholds, asset/model references, UI
preference, autostart preference, and validation timestamps. Audio selectors
use host API/name/direction; PortAudio numeric ids are resolved per run.

Voice assets are discovered only under the user-local JARVIS voice directory.
The base implementation has no implicit downloader: provisioning requires an
approved, injected provider, is cancellable, and cannot fetch Qwen or a model
collection.

Existing llama.cpp binaries are searched only under the user-local JARVIS
runtime directory. Existing GGUF references are searched in the user-local
JARVIS model directory and the bounded legacy model directory already
identified by the Phase 12 inventory; files are referenced in place and never
copied or modified.

## UI and shutdown

The existing local HUD remains the primary experience surface. The native
window is only setup/status/diagnostics control, and the tray reflects the
same lifecycle state. Pause stops the configured microphone and wake boundary
while retaining Core/brain state; resume reopens the same selector. Shutdown
stops the runner, stops only an owned local model process through the existing
supervisor, shuts down Core, removes the HUD server, and releases the lock.

The startup registration is current-user and reversible. It uses `pythonw`
through Windows Script Host so login does not flash a console and contains no
credential or identity secret.

## Acceptance boundary

The automated productization matrix proves setup/reuse/repair, safe config,
single-instance behavior, no-console startup registration, diagnostics, and
sanitized acceptance evidence. Physical microphone speech, wake performance,
audibility, and human voice quality remain operator acceptance items and are
not claimed by automated tests.
