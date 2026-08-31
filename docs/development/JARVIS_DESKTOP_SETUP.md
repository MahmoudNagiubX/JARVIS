# JARVIS desktop setup

The normal product entry point is:

```text
pythonw.exe -m jarvis.desktop
```

The developer entry point remains `python -m jarvis.voice.live` and continues
to use its explicit environment contract. Normal desktop startup does not
require `PYTHONPATH`, `JARVIS_VOICE_*`, copied identity/device ids, copied
credentials, or a manually started model server.

On the first explicit desktop setup, JARVIS resolves the single local owner
and identity, enrolls or reuses `NIGHTFURY Local Desktop`, stores the raw
credential in Windows Credential Manager (DPAPI CurrentUser fallback), writes
safe settings, reconciles default microphone/speaker selectors, and registers
reversible current-user login startup. No credential is printed or shown.
When the existing local voice environment is present, the startup entry uses
that environment's `pythonw.exe`; otherwise it uses the installed product
interpreter.

If the secure credential is missing or invalid after setup, the product shows
`DEGRADED` with `Repair This Device`. Repair uses the existing enrollment
service and does not revoke unrelated devices, reset the database, or copy or
download Qwen.

The window and tray expose setup, HUD, pause/resume, diagnostics, settings,
restart, and quit. Diagnostics reports safe names and PASS/FAIL reasons only.
Voice assets must already be present locally or be supplied by an approved
cancellable provisioning provider; ordinary startup never downloads speech or
brain assets.

The setup discovery is bounded to the existing JARVIS llama.cpp runtime/model
locations and the Phase 12 legacy model directory. It references the existing
Qwen GGUF in place and starts or attaches the one existing
`LlamaCppRuntimeSupervisor` with alias `jarvis-local-qwen`; it does not pull,
copy, or import model weights.

Automated validation for this product is in
`tests/test_phase_thirteen_zero_touch_productization.py`. Physical acceptance
must be completed in the in-app wizard; raw audio, transcripts, TTS bytes, and
window titles are not retained.
