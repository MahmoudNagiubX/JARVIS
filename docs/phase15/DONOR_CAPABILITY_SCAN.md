# Phase 15 Donor Capability Scan

Audit date: 2026-09-01. Candidate directories were searched read-only under `C:\Jarivs\01_foundation_candidates`, `02_agent_runtime`, `03_computer_use`, `04_memory_lab`, `05_goals_workflows`, `06_voice_room`, `07_communications`, `08_engineering`, and `10_legacy`.

| Donor | Exact local evidence inspected | Useful boundary | Decision |
|---|---|---|---|
| Jupyter MCP Server | `C:\Jarivs\08_engineering\jupyter-mcp\ARCHITECTURE.md`, `README.md`, `jupyter_mcp_server\capabilities.py`, `identity.py`, `audit.py` | Stdio/HTTP mode separation, notebook scope, capability discovery, identity and audit concepts | Reference only; no source/dependency copied |
| Playwright MCP | `C:\Jarivs\03_computer_use\playwright-mcp\server.json`, `SECURITY.md`, `README.md`, `LICENSE` | Stdio packaging and browser tool surface | Reference only; reuse JARVIS BrowserActionService and injected controller |
| OpenJarvis | `C:\Jarivs\02_agent_runtime\openjarvis\LICENSE`, `pyproject.toml` | Provider/agent breadth comparison | Reject as runtime spine; no source/dependency copied |
| Hermes Agent | `C:\Jarivs\02_agent_runtime\hermes-agent\LICENSE`, `README.md` | Hosted/terminal worker comparison | Reference only; no source copied |
| OpenClaw | `C:\Jarivs\07_communications\openclaw\LICENSE`, `README.md` | Gateway/channel and ACP comparison | Reference only; existing OpenClaw adapter remains deferred |
| Microsoft UFO | `C:\Jarivs\03_computer_use\microsoft-ufo` | Windows computer-use comparison | Reject for Phase 15 source reuse; license and host surface are not cleared |
| KiCad MCP | `C:\Jarivs\08_engineering\kicad-mcp\LICENSE`, `README.md`, `src\kicad_mcp\server.py` | Specialist engineering adapter comparison | Reference only; preserve injected EngineeringService provider |
| UI reference donors | `C:\Jarivs\09_ui_reference` and existing Phase 14 salvage records | Presentation comparison | No new source/assets; preserve Phase 14 product-owned UI |

The scan found no donor whose license, security model, and authority model justify copying source into the product. The implementation will use narrow product-owned adapters informed by these boundaries.
