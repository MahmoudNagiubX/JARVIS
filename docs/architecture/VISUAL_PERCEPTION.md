# Visual perception

`PerceptionService` provides on-demand screen/window observation behind an
injected `PerceptionProvider`. It checks the existing identity/device policy
path and emits capture, OCR, and failure events. The service never enables
continuous capture, never stores raw frames, and returns metadata/text/typed
regions only.

Provider priority for later deployments is native/UIAutomation, browser DOM,
OCR, local vision, then visual fallback. OmniParser and UI-TARS are reference
boundaries only. The default provider is the zero-download native Windows
adapter when available and deferred on other platforms. Camera is
architecture-only and continuous camera capture is off.

Phase 10 closes the native workstation path. `WindowsDesktopProvider` uses
typed `ctypes` calls to `user32`, `gdi32`, and `kernel32` for bounded desktop
metadata and on-demand GDI capture. `TransientFrame` is an internal buffer,
never a persistence contract, and is released on every analyzer path.

`PerceptionService` remains the single authority. Its `PerceptionPrivacyPolicy`
is fail-closed for secure/credential windows and supports `off`,
`metadata_only`, and `on_demand`. `DesktopPerceptionRouter` reuses the Phase
09 satellite transport for protocol-v2 structured perception and never sends
raw image bytes. The in-memory cache and ephemeral ToolRegistry retention
classification prevent visual text from entering durable run context,
events, audit, Memory, World State, or HUD state.
