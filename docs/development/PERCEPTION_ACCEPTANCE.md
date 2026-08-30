# Phase 10 perception acceptance

The native Windows provider uses `user32`, `gdi32`, and `kernel32` through
`ctypes`. It observes the active window, bounded visible top-level windows,
window bounds, process name, and display size. Screen capture is on-demand
only and releases its transient BGRA buffer after deriving dimensions and a
digest.

Run from the repository root:

```powershell
$env:PYTHONPATH = 'src'
python -m unittest tests.test_phase_ten_active_perception -v
python -m unittest tests.test_phase_nine_authority_integration tests.test_phase_nine_transport tests.test_phase_nine_http -v
python -m unittest tests.test_phase_eight_final_closure tests.test_phase_eight_integration -v
```

The focused suite covers privacy modes, target capability/owner/status
checks, cache isolation and expiry, frame cleanup, raw-result rejection,
ephemeral agent retention, native metadata bounds, and no automatic capture.
Tesseract, accessibility packages, FFmpeg, local vision, and camera remain
deferred unless an actual installed capability is independently verified.

Physical acceptance must not save a screenshot or type private data. A safe
Notepad launch may be used to verify existing computer authority followed by
metadata observation. Record only bounded dimensions, process name, latency,
provider, and pass/deferred status.
