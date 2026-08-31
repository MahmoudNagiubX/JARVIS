# Donor UI and product salvage report

The local donor inventory was inspected before implementation. No donor source,
asset, icon, font, model, or runtime dependency was copied into JARVIS. The
Phase 14 UI is a small dependency-free product-owned static surface because
the installed environment had no Node/npm runtime and the available donors
introduced larger dependency or authority surfaces than this phase needs.

| Donor | Component/file | License | Value | Decision | Destination |
|---|---|---|---|---|---|
| `01_foundation_candidates/acefelix-jarvis` | UI and CLI patterns | MIT | Lightweight local UI ideas | Reference only; no source copied | None |
| `01_foundation_candidates/personal-jarvis` | UI structure and product framing | Apache-2.0 current release; historical NOTICE reviewed | Product surface comparison | Reference only; no source/assets copied | None |
| `02_agent_runtime/openjarvis` | React/Tauri frontend | Apache-2.0 | Mature but broad frontend/runtime surface | Reject for this phase; dependency and host complexity | None |
| `02_agent_runtime/hermes-agent` | Setup UI patterns | MIT | Local setup flow comparison | Reference only; no source copied | None |
| `03_computer_use/microsoft-ufo` | Computer-use reference | License not treated as cleared for copying | Useful capability comparison | Reject until file-level license is verified | None |
| `03_computer_use/playwright-mcp` | Browser/MCP reference | License evidence present locally | Adapter boundary comparison | Reference only; Phase 15 scope | None |
| `06_voice_room/linux-voice-assistant` | Voice/satellite patterns | Apache-2.0 | Voice lifecycle comparison | Reference only; physical acceptance deferred | None |
| `07_communications/openclaw` | Gateway/channel patterns | MIT | Multi-device comparison | Reference only; no gateway copied | None |
| `08_engineering/jupyter-mcp` | Engineering context patterns | BSD-3-Clause | Worker/workspace comparison | Reference only; no code copied | None |
| `09_ui_reference/panpenek-jarvis` | UI reference | No root license evidence surfaced | Visual comparison only | Reject for source/assets; no copy | None |
| `09_ui_reference/raghava-jarvis` | UI reference | MIT | Visual comparison only | Reference only; no source copied | None |

The resulting frontend uses original dark technical styling, no Marvel assets,
no donor components, no CDN, and no cloud frontend runtime. Consequently no
Phase 14 donor notice file is required beyond this explicit salvage report and
the repository inventory update.
