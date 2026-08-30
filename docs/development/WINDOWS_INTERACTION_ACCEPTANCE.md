# Windows interaction acceptance

Phase 11 acceptance is limited to a harmless interactive desktop session.
Use the existing Core `ComputerActionService` path and an enrolled owner-bound
Windows device. Do not use shell commands, coordinates, arbitrary key codes,
or private clipboard text.

1. Observe desktop metadata, retain the returned `window_ref`, minimize the
   selected Notepad window, verify the iconic state, restore it, and verify
   the restored state.
2. Save a harmless pre-existing clipboard value only in the current process if
   possible. Write `JARVIS_PHASE_11_CLIPBOARD_ACCEPTANCE`, read it back through
   the approval path, compare digest and length, then restore the original
   value when available. Never write the original value to a log or evidence
   file.
3. Observe and focus the Notepad reference, request approval, and type
   `JARVIS PHASE 11 INPUT ACCEPTANCE`. Record execution success separately from
   verification; keyboard input has no readback in this boundary.
4. If volume adjustment is exercised, use one small down/up pair and leave the
   original user volume unchanged. Mute/unmute must not be reported as
   verified unless a truthful state query exists.

Evidence contains only operation status, verification state, bounded counters,
and error codes. It must not contain private text, raw HWND values, clipboard
contents, screenshots, or credentials. A same-host satellite process may be
used to validate the existing typed route, but it is not evidence of a second
physical host.
