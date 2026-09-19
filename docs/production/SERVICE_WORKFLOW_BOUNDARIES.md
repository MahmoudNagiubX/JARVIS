# Service workflow boundaries

The P3 workflow helpers are bounded adapters over the existing JARVIS
authorities. They do not create a second computer, browser, approval, or
message-delivery authority.

## Current code-controlled boundary

- Installed desktop applications are resolved through
  `InstalledApplicationRegistry` and acted on through
  `ComputerActionService`.
- Native desktop open/focus helpers use an opaque `app_ref`, revalidate the
  target through the registry, and require a fresh `application_status`
  readback before returning `READY`.
- Media and service targets require one exact visible match. Ambiguous,
  missing, stale, recent, or first-result targets fail closed.
- Discord destinations are explicit `channel:<id-or-alias>` or
  `dm:<id-or-alias>` references. WhatsApp defaults to the owner self-chat.
- Notion and ChatGPT choose the verified native surface first, then the
  existing Browser V2 surface; unavailable surfaces return
  `SERVICE_SURFACE_BLOCKED`.
- Gmail remains draft-first and does not expose a recipient value in a public
  receipt.

## Deliberately not claimed

The helpers are not owner login evidence and do not silently send, edit, or
play external content. Real semantic actions remain behind the canonical
approval and verification path until the corresponding installed app/browser
surface, owner configuration, and physical readback are available. The final
acceptance state for Spotify, Discord, WhatsApp, OneNote, Notion, ChatGPT,
Gmail, Brave, and YouTube is therefore still owner/configuration or physical
acceptance work, not a fixture pass.

Deterministic tests cover exact resolution, ambiguity, unsafe destination
rejection, native opaque-reference usage, and fresh status readback. They do
not substitute for authenticated owner-service acceptance.
