# Mega Phase 10 review

Phase 10 adds active desktop perception and ephemeral visual context on top of
the closed Phase 09 topology. The existing `PerceptionService`, permission
engine, EventBus, scheduler, computer action service, and satellite transport
remain the authorities.

Implemented boundaries:

- native Windows metadata and on-demand GDI capture with transient release;
- privacy modes `off`, `metadata_only`, and `on_demand`;
- owner/device/session-bound in-memory observation cache;
- safe active-app World State projection with unchanged-sample coalescing;
- `desktop.context.read`, `screen.observe`, and `screen.latest` in the
  existing ToolRegistry;
- ephemeral visual tool retention and explicit visual-reference grounding;
- typed satellite protocol v2 with `perception.screen` and structured results;
- no wrong-screen fallback, raw HWND input, raw image transport, or automatic
  pixel monitoring.

Accessibility, OCR, Arabic OCR, local image-model inference, and camera remain
deferred because the workstation inventory found no usable installed runtime.
Browser DOM remains a structural bridge through the existing BrowserAction
Service; it does not rasterize a physical browser window.

Initial Phase 10 closure evidence before the independent review remediation
(2026-08-30):

- Phase 10 focused matrix: 23 passed, 0 failed;
- Phase 08 regression: 13 passed, 0 failed;
- Phase 09 regression: 39 passed, 0 failed;
- full repository suite: 139 passed, 0 failed;
- `python -m compileall src tests`: PASS;
- `git diff --check`: PASS;
- native Windows probe: active/visible metadata and on-demand GDI capture PASS;
  the transient frame was released and no screenshot file was created.

The final diff review found one `PerceptionService`, one EventBus, one
background scheduler, and one VoiceCore composition path. No SQL/migration
files were changed, and no raw pixel or base64 image payload is persisted or
sent through the typed satellite result channel. OCR, accessibility, local
vision, camera, and a second physical satellite remain deferred.

## Independent GitHub Review Remediation

The targeted remediation closed the remaining perception privacy, topology, and
grounded window-continuity gaps without introducing a second authority:

- canonical DeviceFabric/registry topology now selects the satellite even when
  request and target device IDs are equal; an offline known satellite fails
  closed and never falls back to the Core-local display;
- `desktop.context.read` is explicitly `EPHEMERAL`, so full bounded window
  metadata reaches only the current model turn and durable stores receive the
  normal placeholder/digest;
- the satellite perception provider and computer controller share one provider
  instance, and the legacy `/perception/window` path delegates to canonical
  `observe_screen` authorization;
- `screen.latest` resolves and authorizes an explicit remote target, while
  window references revalidate TTL, visibility, PID, and window class before
  focus or capture.

Final remediation evidence:

- Phase 10 focused remediation matrix: 31 passed, 0 failed;
- Phase 08 regression: 13 passed, 0 failed;
- Phase 09 regression: 39 passed, 0 failed;
- full repository suite: 147 passed, 0 failed, 0 errors;
- `python -m compileall src tests`: PASS;
- `git diff --check`: PASS.

The focused matrix covers all 13 required review categories, including same-ID
satellite online/offline routing for both context and screen, the exact private
title sentinel through the real agent path, shared remote observe-to-focus
continuity, canonical legacy capture denial, remote latest-target isolation,
and deterministic HWND/PID/class reuse rejection. The final review still found
one EventBus, one background scheduler, one VoiceCore composition path, one
PerceptionService, no SQL/migration changes, no ID-inequality perception
routing, and no raw pixel/base64 satellite result or durable desktop-title
output.
