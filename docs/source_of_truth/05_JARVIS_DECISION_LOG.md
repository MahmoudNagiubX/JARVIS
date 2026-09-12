# JARVIS — DECISION LOG

**Status:** CANONICAL ACCEPTED / SUPERSEDED DECISIONS  
**Reviewed:** 2026-09-12

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
| OPEN-002 | exact OCR/visual grounding model/adapter | evaluate after semantic UIA baseline; must fit hardware/privacy |
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
