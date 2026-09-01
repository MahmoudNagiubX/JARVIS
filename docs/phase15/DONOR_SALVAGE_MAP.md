# Phase 15 Donor Salvage Map

No Phase 15 donor source is copied. This map records the allowed salvage at the contract/behavior level.

| Boundary | Donor observation | Product-owned destination | Rejected material |
|---|---|---|---|
| MCP transport | Jupyter MCP and Playwright MCP expose stdio package boundaries | `src/jarvis/mcp` stdio client/configuration | Donor SDKs, remote HTTP defaults, hosted endpoints |
| Capability metadata | Jupyter MCP separates discovery/capability information from execution | Normalized JARVIS capability metadata and existing registries | Donor tool classes and authority decisions |
| Notebook scope | Jupyter MCP documents notebook identity and scoped operations | Existing EngineeringWorkspace/EngineeringService injection | Arbitrary notebook/kernel execution |
| Browser | Playwright MCP provides a rich browser tool catalog | Existing BrowserActionService plus local deterministic controller | BrowserAgentV2, visual default, donor browser runtime |
| Workers | Hermes/OpenClaw describe worker/gateway seams | Existing DeveloperWorkerGateway and WorkerCoordinator | Gateway/channel runtime, shell delegation |
| UI health | Existing Phase 14 projection/UI provides the product surface | Existing ExperienceProjection and Command Center | Donor frontend, remote assets, fake live state |

Every future adaptation must add exact file/version/license evidence to `docs/THIRD_PARTY_INVENTORY.md` before code is copied.
