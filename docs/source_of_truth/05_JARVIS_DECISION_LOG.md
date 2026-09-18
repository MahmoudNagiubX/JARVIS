# JARVIS — DECISION LOG

**Status:** CANONICAL ACCEPTED / SUPERSEDED DECISIONS  
**Reviewed:** 2026-09-18

> Record durable architecture/product decisions here. Do not put ordinary implementation status here.

## 1. Accepted / locked decisions

| ID | Decision | Status | Reason / implication |
|---|---|---|---|
| DEC-001 | JARVIS is a personal AI OS, not a chatbot-with-plugins | `LOCKED` | one coherent assistant presence and runtime |
| DEC-002 | local-first, free-runtime, offline-capable | `LOCKED` | cloud may never be a hidden requirement for core use |
| DEC-003 | one logical authority per domain | `LOCKED` | prevents spaghetti/contradictory state |
| DEC-004 | NIGHTFURY hosts authoritative Core/SQLite/AgentRuntime/VoiceCore/local model | `LOCKED` | accepted Option A topology |
| DEC-005 | VENOM is lightweight infrastructure/execution, not a second brain | `LOCKED` | weak hardware + single-authority principle |
| DEC-006 | SQLite remains current authoritative single-writer DB | `LOCKED_UNTIL_EVIDENCE` | no PostgreSQL migration merely for architecture preference |
| DEC-007 | UI/Command Center is read-only projection, never authority | `LOCKED` | backend truth only |
| DEC-008 | Memory and World State are distinct | `LOCKED` | durable owner knowledge vs fresh expiring observations |
| DEC-009 | external/browser/research/MCP/device content is untrusted data | `LOCKED` | prompt-injection boundary |
| DEC-010 | untrusted external content cannot become durable owner Memory automatically | `LOCKED` | candidate/evidence first; owner/trusted source acceptance required |
| DEC-011 | no unrestricted shell as main-agent capability | `LOCKED` | least privilege and auditability |
| DEC-012 | all side effects use canonical permission/approval/audit path | `LOCKED` | agents/adapters cannot bypass authority |
| DEC-013 | physical success requires physical evidence | `LOCKED` | no fake PASS from mocks/tests |
| DEC-014 | one orchestrator + least-privileged specialist workers; no uncontrolled swarm | `LOCKED` | simpler reasoning/authority model |
| DEC-015 | Security Guardian is deterministic policy first, not LLM authority | `LOCKED` | security decisions must not depend on free-form generation |
| DEC-016 | Computer Use priority: API/native → UIA → app semantic → visual → native input → PyAutoGUI fallback | `LOCKED_DIRECTION` | reliability before coordinate guessing |
| DEC-017 | Windows UI Automation is the semantic desktop foundation | `LOCKED_DIRECTION` | stable controls/properties/patterns |
| DEC-018 | `winapp ui` is a preferred evaluation adapter, not a core dependency | `CANDIDATE` (historical context — see DEC-046) | useful but public preview/replaceable; the production backend choice is now locked by DEC-046, which reaches the same "not a core dependency" conclusion with real evaluation evidence |
| DEC-019 | bounded native SendInput-style layer for low-level mouse/keyboard | `LOCKED_DIRECTION` | real input only after grounding/policy |
| DEC-020 | PyAutoGUI is compatibility/prototype fallback only | `LOCKED` | do not make coordinate automation the architecture |
| DEC-021 | Playwright is the preferred primary live browser backend | `LOCKED_DIRECTION` | DOM/accessibility/actionability and isolated contexts |
| DEC-022 | Selenium is optional legacy/WebDriver compatibility | `OPTIONAL` | not equal primary architecture |
| DEC-023 | browser/research are separate capabilities even when they share Playwright | `LOCKED` | research needs evidence/provenance, browser needs action safety |
| DEC-024 | preferred web extraction is layered static fetch/parser/main-content + Playwright dynamic | `LOCKED_DIRECTION` | use the cheapest deterministic method that works |
| DEC-025 | MCP is adapter/discovery, not authority | `LOCKED` | normalize through existing Tool/Skill + policy path |
| DEC-026 | do not inject all discovered tools into local model context | `LOCKED` | bounded schemas/context and injection resistance |
| DEC-027 | automation reuses BackgroundScheduler/EventBus/AgentRuntime; no second scheduler | `LOCKED` | one temporal/execution authority |
| DEC-028 | goals and missions are distinct | `LOCKED` | durable desired outcome vs bounded executable plan |
| DEC-029 | long missions are budgeted/checkpointed/cancellable and restart-safe | `LOCKED` | no unbounded LLM loops/replayed side effects |
| DEC-030 | credentials/secrets are not Memory | `LOCKED` | encrypted/OS credential storage + opaque references |
| DEC-031 | Voice uses the same VoiceCore/AgentRuntime/authority as text | `LOCKED` | no second voice brain |
| DEC-032 | Egyptian Arabic is primary conversation target, English secondary, mixed technical speech supported | `LOCKED_PRODUCT` | owner UX requirement |
| DEC-033 | no real actor voice cloning | `LOCKED` | synthetic/local distinct voice |
| DEC-034 | raw audio/screenshots/camera/secrets/sensitive args are transient by default | `LOCKED` | privacy/data minimization |
| DEC-035 | Home/device state goes to World State, not Memory directly | `LOCKED` | fresh physical state expires |
| DEC-036 | remote node commands are typed/scoped/expiring; no arbitrary remote shell | `LOCKED` | device-fabric safety |
| DEC-037 | explicit bounded trusted CIDR override may support owner's unusual LAN; never hardcode it | `LOCKED` | preserve secure defaults |
| DEC-038 | llama.cpp is preferred current local GGUF foundation behind ModelRouter | `PREFERRED` | works with current NIGHTFURY constraints |
| DEC-039 | Ollama optional convenience; vLLM future stronger node only | `OPTIONAL` | keep model provider replaceable |
| DEC-040 | exact model files are benchmark choices, not architecture | `LOCKED` | avoid model-name coupling |
| DEC-041 | no JARVIS runtime dependency on AntiGravity/OpenFlow/Google auth | `LOCKED` | development delegation != product dependency |
| DEC-042 | future new screenshots/features extend Capability Registry/roadmap; they do not casually rewrite core authority | `LOCKED` | prevents feature requests causing architecture drift |
| DEC-043 | historical Mega Phase numbering remains 1–19; new work uses Phase 18 workstreams, not invented mega phases | `LOCKED_PROCESS` | keeps continuity readable |
| DEC-044 | Phase 18 begins with a baseline audit/stabilization gate before new capability merges | `ACCEPTED_2026-09-12` | catch drift/debt before larger Computer Use work |
| DEC-045 | the seven-file Source Pack is the default bootstrap; the 2 MB Master is historical archive | `ACCEPTED_2026-09-12` | reduce context confusion/token waste |
| DEC-046 | Computer Use V2 semantic Windows control uses a product-owned in-process Python UIA adapter based on `uiautomation`/`comtypes`. Microsoft `winapp ui` remains optional developer/evaluation tooling and is not a production runtime dependency. | `ACCEPTED_2026-09-12` | resolves OPEN-001; evidence: A1 real-NIGHTFURY evaluation (`docs/audits/PHASE_18_WORKSTREAM_A1_UIA_BACKEND_EVALUATION.md`) — in-process warm-call latency (~10-50ms vs. `winapp`'s ~250-350ms per call, since `winapp` has no persistent-process mode), `pyproject.toml`-pinnable/reproducible dependency, Python testability/mockability behind a product-owned adapter; `winapp` scored stronger on out-of-the-box staleness/verification ergonomics and app-coverage breadth but is a machine-level, non-pinnable, per-call-billed tool better suited to developer/CI inspection than the production agent loop |
| DEC-047 | Computer-use file operations (`inspect_file`/`search_files`/`open_file`/`open_folder`) are confined to explicit owner-configured approved roots (`FileAccessPolicy`, fail-closed with no default root), never an implicit default like the home directory or current working directory. | `ACCEPTED_2026-09-13` | resolves GAP-0503 (path-confinement scope); evidence: Phase 18 Workstream A Batch 03 Milestone 1 (`docs/audits/PHASE_18_WORKSTREAM_A_BATCH_03.md`) — component-wise root containment (verified sibling-prefix-confusion resistant), symlink/junction escape verified denied via `Path.resolve()`'s real-target canonicalization (tested with an actual Windows junction), component/filename-aware sensitive-path deny list as defense in depth. Write/move/copy/rename/delete and file-dialog automation remain explicitly out of scope pending future work. |
| DEC-048 | Read-only local OCR visual grounding (`computer.visual.read`: `ocr_window`/`ocr_element`) uses EasyOCR 1.7.2 (PyTorch 2.14.0+cpu, local CPU inference, combined `Reader(["ar","en"])` for Arabic+English together) as an optional `computer-ocr` dependency group, behind a product-owned `EasyOcrVisualAdapter`. PaddleOCR and RapidOCR were both evaluated and rejected. | `ACCEPTED_2026-09-13` | resolves OPEN-002; advances GAP-0103 to `PARTIAL` (read-only only - no visual actuation); evidence: Phase 18 Workstream A Batch 05 Milestones 0-1 (`docs/audits/PHASE_18_WORKSTREAM_A_BATCH_05.md`) — PaddleOCR 3.7.0+paddlepaddle 3.3.1 crashes on every prediction with a reproducible PaddlePaddle CPU oneDNN executor bug on this machine, unresolved after multiple remediation attempts; RapidOCR 3.9.2's only Arabic recognition tier scores far under the required 0.85 recall gate even with corrected (`arabic_reshaper`+`python-bidi`) fixture rendering, and independently reproduced a known undeclared `python-bidi` dependency risk; EasyOCR scored 1.0 normalized recall on all 7 English/Arabic/mixed fixtures across 3 reproducible runs, ~0.2-0.5s warm latency (well under the 3s gate), Apache-2.0 licensed, no cloud/API key, deterministic provider seam (`reader_factory` injection) proven mockable in the full test suite. Real, physical proof against a JARVIS-owned Win32 fixture (both `ocr_window` and `ocr_element`, 3/3 clean runs) confirms the GDI-capture → numpy-array-conversion → OCR-inference pipeline works end to end, not just against clean synthetic benchmark images. Footprint (~1.26 GB with cached models) is real and only paid by an owner who explicitly installs the optional dependency; core JARVIS startup and every other Computer Use capability are unaffected when it is absent. Visual references are observation-only this batch - no visual actuation exists. **Batch 06 hardening (decision unchanged - EasyOCR 1.7.2 remains accepted):** production `Reader()` construction now always passes `download_enabled=False` plus an explicit, product-owned model directory (`JarvisConfig.ocr_model_dir`/`JARVIS_OCR_MODEL_DIR`, no implicit `~/.EasyOCR` fallback, verified before `Reader()` is ever constructed) - closing R18B05-001. Reproducibility (R18B05-002) is closed by pinning `torch==2.14.0`/`torchvision==0.29.0` alongside `easyocr==1.7.2` in `pyproject.toml`'s `computer-ocr` extra - the exact CPU-only build (`torch.version.cuda is None`) DEC-048's original evidence was produced on, re-verified by a fresh install into a disposable isolated venv (plain PyPI, no alternate index). A unified live-GUI physical proof of Arabic/mixed OCR (Batch 06 Milestone 1, a third owned fixture rendering real Arabic Unicode through Windows' own live text shaping) confirms both pure-Arabic labels recognized with an exact match, 3/3 runs, no change to the provider choice. |

| DEC-049 | Anonymous browser work uses isolated ephemeral contexts. Authenticated owner workflows use a dedicated JARVIS-owned persistent Brave profile, manually authenticated by the owner after an explicit local opt-in. The normal Brave profile is never imported or attached; cookies, tokens, credentials, and profile databases remain non-model-visible and non-audited. | `ACCEPTED_2026-09-18` | resolves GAP-0205 at the policy/physical-gate level; evidence: Phase 18 Workstream B Batch 10 T2 (`docs/audits/PHASE_18_WORKSTREAM_B_BATCH_10.md`) - exact verified Brave executable, two controlled owner-persistent launches, clean context/runtime shutdown, dedicated profile reuse, and no process attributable to that dedicated profile after close. |
| DEC-050 | The release candidate is the single-machine NIGHTFURY JARVIS Desktop Product. External hardware and optional distributed services are non-blocking only when their states remain truthfully `NOT_CONFIGURED`, `PHYSICAL_PENDING`, or `OPTIONAL`. | `ACCEPTED_2026-09-18` | establishes the final desktop release scope without weakening the one-authority, local-first, physical-evidence, or fail-closed invariants |
| DEC-051 | Codex CLI may be launched as an optional developer worker only when `JARVIS_CODEX_WORKER_ENABLED=true`, an owner-approved Git workspace is supplied, the run is time/output bounded and process-owned, and the request remains on the existing `WorkerCoordinator` / `DeveloperWorkerGateway` / audit path. Codex is not a startup dependency and cannot become JARVIS authority. | `ACCEPTED_2026-09-18` | closes the selected safe adapter policy while preserving explicit owner opt-in, canonical approvals for any future write mode, and independent verification |
| DEC-052 | Installed desktop applications are the preferred local application surface. A bounded `InstalledApplicationRegistry` may discover only standard Start Menu/App Paths/known-app identities and expose opaque `app_ref` descriptors; `ComputerActionService` remains the sole launch/focus authority with exact target revalidation, fresh window/foreground verification, owner settings, and local-only enforcement. Browser page control remains under `BrowserActionService`; no Tier A/B application workflow is accepted without physical evidence. | `ACCEPTED_2026-09-19` | native desktop addendum `d6848c1`; deterministic registry/boundary evidence is green, while the generic-app physical focus probe remains launch-only and fail-closed |

## 2. Superseded historical decisions/states

### SUP-001 — Phase 17 HOLD at `db3f61a`
**Old state:** 2026-09-05 Master said Phase 17 required one last real-network closure.  
**Superseded by:** `54b67ba396ec45180f1b60ea472ef94c9ac181a9` (`fix: close phase 17 real network readiness`).  
**Current truth:** code/architecture/network-readiness closure is pass; physical gates remain separate.

### SUP-002 — Legacy topology with VENOM as central Core/database host
**Old state:** older BMO/VENOM architecture placed central services on Lenovo/VENOM.  
**Superseded by:** accepted Option A final JARVIS topology.  
**Current truth:** NIGHTFURY is authority; VENOM is infrastructure node.

### SUP-003 — PostgreSQL/pgvector as expected central storage
**Old state:** older legacy plans referenced PostgreSQL/pgvector.  
**Superseded by:** final accepted SQLite single-writer deployment.  
**Current truth:** do not migrate without new evidence/approval.

### SUP-004 — Visual/coordinate automation as default computer-use strategy
**Old possibility:** donor tools/prototypes could imply coordinate-first automation.  
**Superseded by:** deterministic/native/UIA-first Computer Use V2 direction.

### SUP-005 — Selenium/PyAutoGUI as mandatory choices
**Old possibility:** these were examples considered by the owner, not mandates.  
**Current truth:** Playwright is primary browser direction; UIA/native is primary Windows direction; Selenium/PyAutoGUI are fallbacks/compatibility only.

## 3. Decisions still open

These are intentionally **not** locked yet:

| ID | Decision needed | Gate |
|---|---|---|
| ~~OPEN-002~~ | ~~exact OCR/visual grounding model/adapter~~ | **CLOSED by DEC-048** (2026-09-13, Batch 05) - EasyOCR 1.7.2 selected after PaddleOCR/RapidOCR both failed corrected acceptance gates; see DEC-048 in Section 1 for full evidence. Batch 04's PaddleOCR/RapidOCR-blocked evaluation evidence remains historically preserved in `docs/audits/PHASE_18_WORKSTREAM_A_BATCH_04.md` Section 5. |
| OPEN-003 | exact live email provider | owner account/provider choice + secure credential path |
| OPEN-004 | exact calendar provider | owner account/provider choice + secure credential path |
| OPEN-005 | exact external developer worker adapter | only if safe/live use case is required |
| OPEN-006 | exact personal-data schemas/fields | after Mahmoud supplies curated data |
| OPEN-007 | exact future phone/mobile client | after priority/use case is defined |
| OPEN-008 | exact Home Assistant/MQTT deployment details | physical environment/configuration |
| OPEN-009 | exact UI capability additions from new screenshots | after screenshots are reviewed |
| OPEN-010 | repository governance level (branch rules/signing details) | Phase 18 practical solo-dev decision |
| OPEN-011 | final local Egyptian TTS model/voice | benchmark quality/licensing/resources |

## 4. Decision-change procedure

To change a locked decision:
1. identify the decision ID;
2. provide evidence/reason the current decision blocks correctness, safety, performance, or owner goals;
3. describe migration and affected services/tests/docs;
4. obtain explicit owner approval;
5. append a new decision and mark the old one `SUPERSEDED`;
6. update core/current-state/roadmap only where necessary;
7. never silently “refactor” a locked decision away.
