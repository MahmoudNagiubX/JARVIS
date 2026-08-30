# Phase 11 Windows interaction inventory

Inventory date: 2026-08-30

| Check | Result |
|---|---|
| Operating system | Microsoft Windows NT 10.0.26200.0 |
| Interactive desktop session | PowerShell session 1; foreground-window API returned a live handle during the probe |
| Native window API | `user32.dll`: `ShowWindow`, `IsIconic`, `IsZoomed`, `GetForegroundWindow`, and `SetForegroundWindow` available |
| Native input API | `user32.dll!SendInput` available; Unicode `KEYEVENTF_UNICODE` path is implemented and bounded |
| Native clipboard API | `user32.dll`: `OpenClipboard`, `GetClipboardData`, `EmptyClipboard`, and `SetClipboardData`; `kernel32.dll`: `GlobalAlloc`/`GlobalLock` available |
| Audio control | Bounded media-key injection is available; reliable mute-state query is not available in the free native boundary, so mute/unmute remains `audio_state_unavailable` |
| Accessibility/UI automation | No installed `pywinauto` runtime found; accessibility automation remains deferred |
| Screen/perception | Existing Phase 10 native metadata and on-demand GDI provider is reused; continuous capture and OCR remain disabled/deferred |

No credentials, clipboard contents, window titles, raw handles, screenshots, or
other private desktop material are stored in this inventory. Coordinate mouse
control, arbitrary virtual keys, shell execution, and accessibility automation
remain outside Phase 11.
