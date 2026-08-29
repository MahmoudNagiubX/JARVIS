# Third-party inventory

This is the Phase 02 inventory for source references and declared dependency
surfaces. It is not a final distribution notice.

| Source/component | Local evidence | License/status | Phase 02 treatment |
|---|---|---|---|
| BMO/JARVIS | `C:\Users\mahmo\Desktop\BMO\BMO-Personal-AI-OS\LICENSE`, `pyproject.toml` | Apache-2.0 declared | Architectural reference; no source copied |
| PersonalJarvis | `C:\Jarivs\01_foundation_candidates\personal-jarvis\LICENSE`, `NOTICE` | Apache-2.0 for current release; NOTICE says releases through 1.6.0 remain MIT | Donor/reference only; code and bundled assets not copied |
| aceFelix/jarvis | `C:\Jarivs\01_foundation_candidates\acefelix-jarvis\LICENSE`, `pyproject.toml` | MIT | Donor/reference only; code not copied |
| Phase 01 foundation | this repository `pyproject.toml` | Apache-2.0 placeholder; final product license not selected | Original product-owned contracts and tests |
| Python standard library | Python runtime | Python Software Foundation License | SQLite, HTTP, CLI, hashing, and async orchestration |
| Ollama | Existing local service boundary | No SDK copied | Optional loopback model adapter only; no pull/copy/install/delete |
| Existing local Qwen assets | Local assets observed outside this repository | Exact model license not established here | Alias configuration only; no asset copied |

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
- Phase 02 foundation declares no runtime dependencies. Pytest is an optional
  development dependency only; the baseline test command uses the standard
  library `unittest` runner.

## Compliance gates before reuse/distribution

Before copying or adapting donor code, identify the exact files and versions,
retain applicable license/NOTICE text, check bundled model and asset licenses,
review trademarks and contributor terms, and record the result in an updated
inventory. A package license does not automatically license its provider SDKs,
models, or bundled assets. Microsoft UFO is an adapter boundary only and is
not merged in Phase 02.
