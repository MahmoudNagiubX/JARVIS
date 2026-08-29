# Visual perception

`PerceptionService` provides on-demand screen/window observation behind an
injected `PerceptionProvider`. It checks the existing identity/device policy
path and emits capture, OCR, and failure events. The service never enables
continuous capture, never stores raw frames, and returns metadata/text/typed
regions only.

Provider priority for later deployments is native/UIAutomation, browser DOM,
OCR, local vision, then visual fallback. OmniParser and UI-TARS are reference
boundaries only. The default provider is deferred because no local
capture or OCR adapter was configured. Camera is architecture-only and
continuous camera capture is off.
