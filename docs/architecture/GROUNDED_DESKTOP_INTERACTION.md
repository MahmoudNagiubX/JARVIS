# Grounded desktop interaction

Phase 11 extends the existing `ComputerActionService` with a deliberately
small Windows interaction surface:

- `window_action` supports only minimize, maximize, and restore, and operates
  only on a fresh Phase 10 `window_ref` revalidated for TTL, visibility, PID,
  and class;
- volume changes use only bounded `SendInput` media keys (one to ten steps);
  mute/unmute report `audio_state_unavailable` when native state cannot be
  truthfully queried;
- clipboard access uses native `CF_UNICODETEXT`, a 16,000-code-point limit,
  bounded retries, write readback, and digest/length metadata;
- keyboard input supports only literal Unicode `type_text`, up to 2,000 code
  points, in UTF-16 chunks of at most 64 code units after exact foreground
  verification; coordinates, arbitrary keys, paste, and mouse input are not
  supported.

All actions continue through the single computer permission, approval, audit,
and event boundary. The existing typed satellite transport carries only the
allowlisted operation names. The tool registry exposes narrow computer tools;
handlers delegate to `ComputerActionService` and never call a controller
directly.

Clipboard reads and sensitive keyboard/clipboard-write arguments are
ephemeral. Durable tool rows contain only retention flags, digests, lengths,
and field names. Raw approval arguments exist only in bounded in-memory stores
and are lost on restart. Approval resume checks owner and requesting device,
and delegated computer approvals reuse the domain approval rather than
creating a second approval.
