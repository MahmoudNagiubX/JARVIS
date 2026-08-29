# Third-party inventory

This is the Phase 05 inventory for source references and declared dependency
surfaces. It is not a final distribution notice.

| Source/component | Local evidence | License/status | Phase 03 treatment |
|---|---|---|---|
| BMO/JARVIS | `C:\Users\mahmo\Desktop\BMO\BMO-Personal-AI-OS\LICENSE`, `pyproject.toml` | Apache-2.0 declared | Architectural reference; no source copied |
| PersonalJarvis | `C:\Jarivs\01_foundation_candidates\personal-jarvis\LICENSE`, `NOTICE` | Apache-2.0 for current release; NOTICE says releases through 1.6.0 remain MIT | Donor/reference only; code and bundled assets not copied |
| aceFelix/jarvis | `C:\Jarivs\01_foundation_candidates\acefelix-jarvis\LICENSE`, `pyproject.toml` | MIT | Donor/reference only; code not copied |
| Microsoft UFO | Local donor/reference only | Not merged; license/runtime surface requires later review | Future Windows UI automation adapter boundary only |
| Phase 01 foundation | this repository `pyproject.toml` | Apache-2.0 placeholder; final product license not selected | Original product-owned contracts and tests |
| Python standard library | Python runtime | Python Software Foundation License | SQLite, HTTP, CLI, hashing, and async orchestration |
| Ollama | Existing local service boundary | No SDK copied | Optional loopback model adapter only; no pull/copy/install/delete |
| Existing local Qwen assets | Local assets observed outside this repository | Exact model license not established here | Alias configuration only; no asset copied |
| Mem0 / Cognee / Graphiti | No runtime package selected | Not introduced | Reference-only evaluation; JARVIS memory remains authoritative |
| LangGraph | No runtime package selected | Not introduced | Reference-only evaluation; JARVIS goal engine remains authoritative |
| PostgreSQL / pgvector | Product migration boundary only | No runtime package dependency | Partial/deferred adapter path; no live service claimed |
| Jupyter MCP | `C:\Jarivs\08_engineering\jupyter-mcp\ARCHITECTURE.md`, `README.md` | BSD-3-Clause donor; read-only audit | Capability, scope, and context concepts only; no source copied |
| OpenJarvis | `C:\Jarivs\02_agent_runtime\openjarvis\LICENSE`, `pyproject.toml` | Apache-2.0 donor; broad optional provider surface | Research/agent reference only; no source or dependency copied |
| Hermes Agent | `C:\Jarivs\02_agent_runtime\hermes-agent\LICENSE`, `README.md` | MIT donor; hosted and terminal integrations | Worker/research reference only; no source or dependency copied |
| OpenClaw | `C:\Jarivs\07_communications\openclaw\LICENSE`, `README.md` | MIT donor; broad gateway/channel surface | Multi-device and ACP reference only; no source or dependency copied |
| Linux Voice Assistant | `C:\Jarivs\06_voice_room\linux-voice-assistant\LICENSE.md`, `README.md` | Apache-2.0 donor | Voice/satellite reference only; no source or dependency copied |
| OCR/local vision/OmniParser/UI-TARS | No runtime package selected | Deferred/reference-only | Capability/provider boundaries only; no models downloaded or copied |

## Declared dependency surfaces reviewed

- BMO core declares Alembic, FastAPI, OpenJarvis, psutil, psycopg, Pydantic
  Settings, SQLAlchemy, Uvicorn, and WebSockets; voice adds a substantial
  optional audio/ML stack.
- PersonalJarvis declares a broad provider, audio, media, browser, vision,
  MCP, UI, telemetry, and system integration surface, including optional local
  model and speech components.
- aceFelix/jarvis core declares provider SDKs, Pydantic, terminal UI/config
  dependencies; optional extras add GUI, browser, camera/vision, voice,
  daemon, realtime UI, and channel integrations.
- Phase 04 foundation declares no runtime dependencies. Pytest is an optional
  development dependency only; the baseline test command uses the standard
  library `unittest` runner.

## Compliance gates before reuse/distribution

Before copying or adapting donor code, identify the exact files and versions,
retain applicable license/NOTICE text, check bundled model and asset licenses,
review trademarks and contributor terms, and record the result in an updated
inventory. A package license does not automatically license its provider SDKs,
models, or bundled assets. Microsoft UFO is an adapter boundary only and is
not merged. Playwright, Home Assistant, MQTT, email, Telegram, and Discord are
optional adapter surfaces only; none is a runtime dependency. No Phase 05 donor
repository was modified.
