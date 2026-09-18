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
interpreter. First-run setup installs the local checkout into the existing
voice venv with no dependencies or network access, verifies `import
jarvis.desktop` with `PYTHONPATH` and all `JARVIS_VOICE_*` variables absent, and
creates both the Startup VBS and current-user Start Menu
`Programs\\JARVIS.lnk`. Neither launcher carries a secret.

If the secure credential is missing or invalid after setup, the product shows
`DEGRADED` with `Repair This Device`. Repair uses the existing enrollment
service and does not revoke unrelated devices, reset the database, or copy or
download Qwen.

The window and tray expose setup, HUD, pause/resume, diagnostics, settings,
mic/speaker selectors, transient mic and fixed safe speaker tests, device
repair, the real Start-with-Windows toggle, and the physical acceptance
wizard. Diagnostics reports safe names and PASS/FAIL reasons only. The
acceptance wizard records human observations in sanitized evidence and keeps
physical status `PENDING` until all required steps are explicitly passed.
Voice assets must already be present locally or be supplied by an approved
cancellable provisioning provider; ordinary startup never downloads speech or
brain assets.

The setup discovery is bounded to the existing JARVIS llama.cpp runtime/model
locations and the Phase 12 legacy model directory. It references the existing
Qwen GGUF in place and starts or attaches the one existing
`LlamaCppRuntimeSupervisor` with alias `jarvis-local-qwen`; it does not pull,
copy, or import model weights.

Automated validation for this product is in
`tests/test_phase_thirteen_zero_touch_productization.py` and
`tests/test_phase_thirteen_zero_touch_final_remediation.py`. The tracked-tree
gate is `scripts/verify_clean_tree_import.py`. Physical acceptance must be
completed in the in-app wizard; raw audio, transcripts, TTS bytes, and window
titles are not retained.

## Release handoff

For the current desktop candidate:

1. Launch the current-user `JARVIS.lnk` shortcut.
2. Complete only the Setup items shown by the product.
3. Use the dedicated JARVIS browser profile for any manually authenticated
   service; the normal Brave profile is outside the product boundary.
4. Type or speak a request and wait for an independently verified result.

Owner-specific identifiers, browser destinations, credentials, raw audio,
transcripts, screenshots, and chat/inbox content are not release-documentation
inputs. Authenticated integrations and physical voice acceptance remain
owner-controlled gates and must be recorded as `NOT_CONFIGURED` or
`PHYSICAL_PENDING` until directly proven.
