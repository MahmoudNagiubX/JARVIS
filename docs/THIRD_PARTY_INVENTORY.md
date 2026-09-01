# Third-party inventory

This is the current inventory for source references and declared dependency
surfaces. It is not a final distribution notice.

| Source/component | Local evidence | License/status | Runtime treatment |
|---|---|---|---|
| BMO/JARVIS | `C:\Users\mahmo\Desktop\BMO\BMO-Personal-AI-OS\LICENSE`, `pyproject.toml` | Apache-2.0 declared | Architectural reference; no source copied |
| PersonalJarvis | `C:\Jarivs\01_foundation_candidates\personal-jarvis\LICENSE`, `NOTICE` | Apache-2.0 for current release; NOTICE says releases through 1.6.0 remain MIT | Donor/reference only; code and bundled assets not copied |
| aceFelix/jarvis | `C:\Jarivs\01_foundation_candidates\acefelix-jarvis\LICENSE`, `pyproject.toml` | MIT | Donor/reference only; code not copied |
| Microsoft UFO | Local donor/reference only | Not merged; license/runtime surface requires later review | Future Windows UI automation adapter boundary only |
| JARVIS runtime | this repository `pyproject.toml` | Private development metadata; no final product license selected | Original product-owned contracts and tests |
| Python standard library | Python runtime | Python Software Foundation License | SQLite, HTTP, CLI, hashing, and async orchestration |
| Ollama | Existing local service boundary | No SDK copied | Optional loopback model adapter only; no pull/copy/install/delete |
| llama.cpp | Official `ggml-org/llama.cpp` release `b10690`; local runtime package checksum-verified | MIT; runtime remains user-local and untracked | Explicit loopback `llama_cpp` provider/supervisor; no model-weight download/copy |
| Existing local Qwen assets | Local assets observed outside this repository | Exact model license not established here | Alias configuration only; no asset copied |
| Phase 13 local voice stack | Optional external venv: sounddevice, onnxruntime, openWakeWord, faster-whisper, Piper | Package/model notices are separately documented; no asset is tracked | Explicit local runner only; no normal bootstrap import/download |
| openWakeWord pre-trained assets | External local ONNX assets | CC-BY-NC-SA-4.0; code Apache-2.0 | Personal/non-commercial only; commercial replacement debt |
| Silero VAD ONNX | External local ONNX asset | MIT | Local VAD only |
| Piper English/Arabic voices | External local ONNX assets and model cards | English card cites CC-BY-NC-SA; Arabic card requires source-license review | No commercial or Egyptian-quality claim |
| Mem0 / Cognee / Graphiti | No runtime package selected | Not introduced | Reference-only evaluation; JARVIS memory remains authoritative |
| LangGraph | No runtime package selected | Not introduced | Reference-only evaluation; JARVIS goal engine remains authoritative |
| PostgreSQL / pgvector | Product migration boundary only | No runtime package dependency | Partial/deferred adapter path; no live service claimed |
| Jupyter MCP | `C:\Jarivs\08_engineering\jupyter-mcp\ARCHITECTURE.md`, `README.md` | BSD-3-Clause donor; read-only audit | Capability, scope, and context concepts only; no source copied |
| OpenJarvis | `C:\Jarivs\02_agent_runtime\openjarvis\LICENSE`, `pyproject.toml` | Apache-2.0 donor; broad optional provider surface | Research/agent reference only; no source or dependency copied |
| Hermes Agent | `C:\Jarivs\02_agent_runtime\hermes-agent\LICENSE`, `README.md` | MIT donor; hosted and terminal integrations | Worker/research reference only; no source or dependency copied |
| OpenClaw | `C:\Jarivs\07_communications\openclaw\LICENSE`, `README.md` | MIT donor; broad gateway/channel surface | Multi-device and ACP reference only; no source or dependency copied |
| Linux Voice Assistant | `C:\Jarivs\06_voice_room\linux-voice-assistant\LICENSE.md`, `README.md` | Apache-2.0 donor | Voice/satellite reference only; no source or dependency copied |
| OCR/local vision/OmniParser/UI-TARS | No runtime package selected | Deferred/reference-only | Capability/provider boundaries only; no models downloaded or copied |
| Phase 07 evaluation/anomaly helpers | No runtime package selected | Not introduced | Stdlib deterministic baselines only; no model or cloud grader |
| Phase 14 Command Center frontend | `ui/frontend.lock.json`, `ui/package-lock.json`, `ui/src/` | React 19.2.8, React DOM 19.2.8, React Router DOM 7.18.3; Vite 7.3.6, TypeScript 5.9.3, Vitest 3.2.7; `npm audit`: 0 vulnerabilities | Local compiled assets only at runtime; no remote assets, icons, fonts, CDN, cloud frontend runtime, or donor backend. Three MIT-cleared donor 03 presentation components are adapted with attribution in the Phase 14 donor records. |

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
- The JARVIS runtime declares no runtime dependencies. Pytest is an optional
  development dependency only; the baseline test command uses the standard
  library `unittest` runner.
- Phase 13 declares the local speech stack as a `voice` optional dependency.
  It is deliberately installed in an external venv on the inspected Windows
  workstation; normal `create_runtime()` imports no optional audio package and
  opens no audio/model resource.

## Compliance gates before reuse/distribution

Before copying or adapting donor code, identify the exact files and versions,
retain applicable license/NOTICE text, check bundled model and asset licenses,
review trademarks and contributor terms, and record the result in an updated
inventory. A package license does not automatically license its provider SDKs,
models, or bundled assets. Microsoft UFO is an adapter boundary only and is
not merged. Playwright, Home Assistant, MQTT, email, Telegram, and Discord are
optional adapter surfaces only; none is a runtime dependency. Phase 07 adds no
runtime dependency, downloads no models, and modifies no donor or BMO
repository. Phase 14's donor decisions and exact adapted paths are recorded in
`docs/phase14/DONOR_UI_AND_PRODUCT_SALVAGE.md` and
`docs/phase14/UI_DONOR_SALVAGE_MAP.md`.

## Phase 15 audit update — 2026-09-01

The Phase 15 read-only donor scan found no additional source that is cleared
for copying. Jupyter MCP Server, Playwright MCP, OpenJarvis, Hermes Agent,
OpenClaw, Microsoft UFO, and KiCad MCP remain reference/adaptor evidence only.
Phase 15 will use product-owned stdio and capability normalization boundaries,
preserve the existing JARVIS authority spine, and add no runtime dependency
unless a later focused test and license review require one. Exact decisions are
recorded in `docs/phase15/DONOR_CAPABILITY_SCAN.md` and
`docs/phase15/DONOR_SALVAGE_MAP.md`.

## Phase 14 V2 donor fusion update - 2026-09-01

The nine local UI donor repositories under `C:\Jarivs\14_ui_candidates` were
re-inspected for the V2 refactor. The exact 28-unit reuse decisions, source
paths, destinations, license notes, and reference-only exclusions are recorded
in `docs/phase14/ui-refactor/DONOR_EXTRACTION_MANIFEST.md`. Only presentational
patterns were adapted into product-owned TypeScript components. No donor
runtime, backend, mock data, remote asset, font, icon CDN, WebSocket transport,
identity/profile storage, WebXR loop, or cloud service was copied.

The owner-supplied wallpaper is tracked at
`ui/src/assets/hero/ironman-owner-wallpaper.jpg`; it is used on Home only.
The V2 palette and accessibility rules are recorded in
`docs/phase14/ui-refactor/VISUAL_SYSTEM_V2.md`. Donor 07 and donor 08 had no
license evidence in the inspected roots and donor 02/09 contained runtime or
identity boundaries, so their visual contributions remain reference-only.

## Phase 14 V3 cinematic rebuild update - 2026-09-01

The V3 visual extraction record is `docs/phase14/v3/DONOR_SOURCE_EXTRACTION.md`.
It names the exact donor component/function paths used as presentation
references and records the exclusions. V3 uses the owner-supplied wallpaper as
the only hero artwork and adds product-owned SVG/CSS primitives under
`ui/src/components/{cinematic,holographic,tactical}`. No donor runtime,
WebGL/MediaPipe loop, remote asset, font, cloud service, mock telemetry, or
second transport/state authority was copied. The V3 visual system and before /
after decisions are recorded in `docs/phase14/v3/V3_VISUAL_SYSTEM.md` and
`docs/phase14/v3/V3_BEFORE_AFTER.md`.
