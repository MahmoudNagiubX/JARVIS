# Active desktop context

`ActiveDesktopContextService` is the in-memory situational-context layer for
the current owner/device/session. It keeps the latest bounded desktop snapshot
and explicit observation reference, but it is not a replacement for Memory or
World State.

Only safe metadata may be projected to World State:

```text
desktop.<device>.active_app
desktop.<device>.active_workspace
desktop.<device>.available
```

Window titles, OCR text, document bodies, pixels, and image bytes are never
projected. Unchanged metadata samples are coalesced. Optional background
awareness is disabled by default and, when explicitly enabled, polls metadata
only through the existing `BackgroundScheduler`; it never captures pixels.

Window references are in-process, random, and short-lived. They are not raw
HWND identifiers and must be revalidated before any future grounded control.
