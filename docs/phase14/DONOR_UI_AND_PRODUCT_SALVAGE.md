# Donor UI and product salvage report

The local donor inventory was inspected before implementation. The final UI
adapts only three file-cleared, MIT-licensed presentational components from
donor 03. No donor backend, runtime authority, mock data, model, icon, font,
or remote asset was copied into JARVIS. All data and actions remain behind the
existing JARVIS API and experience projection.

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

The resulting frontend uses product-owned dark technical styling, no Marvel
assets, no CDN, and no cloud frontend runtime. The adapted components are
`ui/src/components/hud/JHudFrame.tsx`, `JArcReactor.tsx`, and `JWaveform.tsx`;
their donor source and MIT treatment are recorded in the Phase 14 salvage map.
