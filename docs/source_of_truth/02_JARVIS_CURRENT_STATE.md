# JARVIS — CURRENT STATE

**Status:** SNAPSHOT / IMPLEMENTATION TRUTH SUMMARY  
**Reviewed:** 2026-09-19
**Repository:** `MahmoudNagiubX/JARVIS`  
**Reviewed HEAD:** `5a0ea52`

> Always compare this file with current HEAD before trusting it in a later chat.

**Final-completion feature-branch checkpoint:** `5a0ea52` — bounded desktop
release slices plus the native installed-application control addendum are
implemented; external/physical release gates remain explicitly partial where
evidence is unavailable.

## 1. Current repository baseline

Current reviewed `main` commit:

```text
54b67ba396ec45180f1b60ea472ef94c9ac181a9
fix: close phase 17 real network readiness
```

Current Phase 17 audit evidence at this commit:

| Check | Result |
|---|---|
| Phase 17 focused tests | 79 passed |
| Phase 13–16 regression | 218 passed + 11 subtests |
| Full Python suite | 514 passed, 1 justified skip, 36 subtests |
| Frontend Vitest | 75 passed |
| Frontend build | PASS |
| npm high-severity audit | 0 vulnerabilities |
| `compileall` | PASS |
| `git diff --check` | PASS |

The commit is recorded as unsigned. A Phase 18 final-completion CI workflow is
now present on the feature branch; hosted execution and required-check branch
protection remain unproven.

### 1.1 Phase 18A audit/stabilization status (2026-09-12)

Phase 18A.1 baseline audit and Phase 18A.2 targeted stabilization ran against
the `54b67ba` baseline; their reviewed results are carried by the repository's
subsequent Phase 18 checkpoints:

- `docs/audits/PHASE_18A1_BASELINE_AUDIT.md` — evidence-based audit; verdict `AUDIT_GATE_PASS_WITH_ROADMAP_GAPS`; 0 P0, 3 P1, 8 P2, 3 P3 findings.
- `docs/audits/PHASE_18A2_STABILIZATION.md` — fixed the 7 approved findings (F18A1-013, 003, 001, 002, 009, 007, 012) with 15 new focused regression tests; full Python suite is green at 530 passed, 0 skipped, 36 subtests (515 pre-existing + 15 new; the one previously-justified skip is environment-dependent per the 18A.1 report and did not trigger in this environment either run). Frontend Vitest (75 passed), build, and `npm audit --audit-level=high` (0 high/critical) remain unchanged/green.
- Deferred findings (F18A1-004, 005, 006, 008, 010, 011, 014) remain open roadmap items — see `03_JARVIS_GAP_REGISTER.md`.
- The repo-local `docs/source_of_truth/*` pack (this file included) was copied into the actual git repository during Phase 18A.2, closing F18A1-013/GAP-0002. It is now authoritative; the parent-directory (`C:\Jarivs\`) originals remain as historical bootstrap source only.

## 2. Phase status

| Phase | Current truth |
|---|---|
| 01–12 | historical implementation/closure complete |
| 13 | `IMPLEMENTED` code/product; `PHYSICAL_PENDING` full voice acceptance |
| 14 Command Center | `IMPLEMENTED` / final pass |
| 15 MCP/Skills/Browser/Research | `IMPLEMENTED` foundation/final pass; some live adapters remain optional/deferred |
| 16 Personal Intelligence | `IMPLEMENTED` / final pass |
| 17 VENOM/Home/Multi-device/Room Fabric | code/architecture + real-network readiness `IMPLEMENTED`; physical deployment gates remain `PHYSICAL_PENDING`/`NOT_CONFIGURED` |
| 18 | Phase 18A baseline/stabilization remains complete; Workstream A Batch 09 T0 visual acceptance is physically green 3/3, `RW-CALC-001` is physically green 3/3 through the explicit owner-session boundary, and Brave binary provenance is recorded. Workstream B Batch 10 T0-T5 are green and T6 is deterministic-security `PARTIAL`: optional Playwright navigation/read/extraction foundation, dedicated ephemeral/owner-persistent session policy, DOM/accessibility-first approval-bound actions, bounded provenance-aware extraction, bounded file-transfer/transient-screenshot workflows, and fail-closed owner-session preflight are implemented and tested. Final-completion W1 fixed the desktop product capability-profile drift in `4f7b679`; Playwright `1.63.0` is available and exact Brave launches, but `chatgpt.com` returns HTTP 403 with no DOM content in the bounded live probe. The installed ChatGPT desktop app is a separate manual surface and does not close Browser V2. |
| 19 | final physical end-to-end acceptance/release not started |

**Important:** the 2026-09-05 Master's Phase 17 HOLD was superseded by the later `54b67ba` closure. Do not re-open those code gaps without regression evidence.

### 2.1 Final-completion local checkpoint (2026-09-18)

The feature branch now carries additional release-candidate slices within the
existing authorities:

- `computer.keyboard.paste` is an explicit, approval-gated bounded insertion
  action. It uses foreground-verified Unicode typing and never reads or
  overwrites the owner clipboard; arbitrary Ctrl+V remains unavailable.
- `SpecialistTaskEnvelope` carries owner/mission/goal/scope/capability,
  budget/deadline/cancellation, evidence, expected-output, and verifier
  requirements to the existing `WorkerCoordinator`. Results carry an explicit
  `executed`/`delivered`/`verified`/`unverified`/`failed` verification state;
  absent an independent verifier, successful provider output remains
  `unverified`.
- Desktop diagnostics now report UI server, browser/profile policy,
  approved-root configuration, Computer Use, scheduler, EventBus, backup,
  notifications, and integration readiness without reading owner content.
- The Command Center engineering surface renders worker verification state.

These are code-backed release improvements; owner-authenticated web, physical
voice/device, and hosted CI/branch-protection evidence remain external gates.

## 3. Capability truth matrix

### Core authority and runtime

| Capability | Status | Current truth |
|---|---|---|
| Owner/device identity | `IMPLEMENTED` | canonical identity/device contracts and enrollment exist |
| Permissions/autonomy | `IMPLEMENTED` | deterministic policy path exists |
| Durable approvals | `IMPLEMENTED` | approval/resume and exactly-once semantics hardened through later phases |
| Audit/events | `IMPLEMENTED` | canonical audit and normalized events exist |
| AgentRuntime | `IMPLEMENTED` | single canonical orchestration path exists |
| ToolRegistry/ToolExecutionService | `IMPLEMENTED` | canonical tool execution boundary exists |
| EventBus/BackgroundScheduler | `IMPLEMENTED` | canonical event/scheduling authorities exist |
| Local offline behavior | `IMPLEMENTED` foundation | product is designed to degrade truthfully without cloud dependencies |

### Local AI/model

| Capability | Status | Current truth |
|---|---|---|
| Local text LLM | `PARTIAL` | Existing llama.cpp/Qwen evidence remains valid; production bootstrap now names the owner-provisioned `Qwen3.5-4B-Heretic` local capability, but no fresh live turn is claimed at this HEAD |
| English/Arabic/mixed text generation | `IMPLEMENTED` | validated in Phase 12 |
| Model-facing bounded tool selection | `IMPLEMENTED` | schema/tool budget exists |
| Local vision model | `PLANNED` | multimodal work is delegated to the optional Gemini provider; no local vision model is claimed |
| Hybrid capability router | `PARTIAL` | deterministic local/Groq/Gemini routing, bounded fallback, cloud-history compaction, transient media, and route events are implemented and tested; provider keys and live cloud acceptance remain disabled/not configured |
| Groq `openai/gpt-oss-120b` provider | `NOT_CONFIGURED` | modular adapter exists; `JARVIS_GROQ_ENABLED` and `GROQ_API_KEY` are owner-controlled and not configured in the repository |
| Gemini `gemini-3.5-flash` provider | `NOT_CONFIGURED` | modular GenerateContent adapter exists with transient inline media; `JARVIS_GEMINI_ENABLED` and `GEMINI_API_KEY` are owner-controlled and not configured |

### Memory/personal intelligence

| Capability | Status | Current truth |
|---|---|---|
| Durable Memory | `IMPLEMENTED` | owner-scoped provenance/confidence/sensitivity/scope/validity/retention/status semantics |
| World State separate from Memory | `IMPLEMENTED` | fresh/expiring state remains separate |
| Memory correction/supersede/delete | `IMPLEMENTED` | Phase 16 closure |
| Untrusted web/research memory firewall | `IMPLEMENTED` | direct persistence fails closed |
| Goals | `IMPLEMENTED` | durable lifecycle/checkpoints |
| Missions | `IMPLEMENTED` | bounded plans, approval consumption, restart reconciliation |
| Automation | `IMPLEMENTED` foundation | declarative rules through existing scheduler/EventBus; no raw shell |
| Proactivity/notifications | `IMPLEMENTED` foundation | deterministic findings + canonical NotificationService bridge |
| Rich manual Personal Knowledge Vault onboarding | `PLANNED` | schema/onboarding UX for Mahmoud's curated data is the Wave D enhancement |

### Computer/files/perception

| Capability | Status | Current truth |
|---|---|---|
| Bounded file/process/app actions | `PARTIAL` | inspect small process list, bounded file read/search/open, allowlisted launch/stop, and the bounded installed-app catalog |
| Installed desktop application control | `PARTIAL` | native-first opaque `app_ref` discovery, exact fingerprinted launch/focus, owner enable/surface settings, and local-only enforcement are implemented. Current physical Notepad evidence proves launch/observation only; foreground focus verification failed closed, so no Tier A/B workflow is claimed. |
| Window focus | `IMPLEMENTED` bounded | fresh `window_ref` revalidation + foreground verification |
| Minimize/maximize/restore | `IMPLEMENTED` bounded | Phase 11 |
| Clipboard Unicode | `IMPLEMENTED` bounded | transient sensitive payload handling/readback |
| Literal Unicode typing | `IMPLEMENTED` bounded | foreground-verified `type_text` |
| Media volume keys | `IMPLEMENTED` bounded | SendInput media-key path |
| Grounded native mouse control | `PARTIAL` | `computer.pointer.act`: `move_to_element`/`left_click_element`/`right_click_element`/`double_click_element`/`scroll_element`/`drag_element_to_element` (bounded `direction`/`steps`, never a raw wheel delta; drag grounded strictly by `source_element_ref`/`target_element_ref`, same-window-only, bounded deterministic interpolation, dual-target approval binding), no raw coordinates, through `WindowsNativeInputAdapter` (Batch 02 Milestone 1, Batch 03 Milestone 2, Batch 04 Milestone 1). Physically proven live on NIGHTFURY through two owned Win32 fixtures, 3/3 each, including a non-primary-monitor click (`NON_PRIMARY_MONITOR_PHYSICAL_PASS`) and a grounded drag (`drag:accepted`). Cross-window drag and file drag/drop remain `PLANNED`. Batch 05 Milestone 2 (GAP-0104) added a single bounded pre-input recovery cycle - one fresh re-ground when grounding fails for a plausibly transient, pre-`SendInput` reason (stale/not-found reference, stale window, unverified focus), never for a policy denial or structural ambiguity, and never once `SendInput` has been called - so a consequential action with an uncertain or possibly-delivered side effect is never auto-retried; see `docs/audits/PHASE_18_WORKSTREAM_A_BATCH_05.md` §5. Batch 06 Milestone 0 closed R18B05-003 - `drag_element_to_element`'s two grounding calls (pre-focus, post-focus) now share exactly one recovery budget per action instead of one each; Milestone 2 physically proved relocation-before-input (fresh bounds used, identity preserved) and approval-identity-change-refused live against a fourth owned fixture, 3/3 each. See `docs/audits/PHASE_18_WORKSTREAM_A_BATCH_06.md` §2.3/§4. |
| Grounded named-key keyboard input | `PARTIAL` | `computer.keyboard.key` (14-key bounded allowlist plus one reviewed `shift+tab` combo), `computer.keyboard.chord` (5-chord allowlist: `ctrl+a/c/f/z/y` only), and the separate approval-gated `computer.keyboard.paste` Unicode-insertion action share the existing grounded-window path. No raw VK/hotkey string or Ctrl+V primitive is exposed. Physical key/typing evidence remains as recorded in the earlier fixture batches; safe insertion is code-backed but has not been claimed as a new physical gate. |
| Paste/drag/drop | `PARTIAL` | element-to-element drag is implemented (see Batch 04); safe bounded insertion is implemented through `computer.keyboard.paste` using Unicode typing without owner-clipboard access; Ctrl+V clipboard paste, file drag/drop, and dialogs remain unavailable/planned |
| UIA semantic control tree/actions | `RESOLVED` (core capability; broader Computer Use V2 breadth continues under GAP-0102/0104/0105/0106) | read (`computer.semantic.read`) and bounded write (`computer.semantic.act`: invoke/toggle/select, approval-required by default) tool paths implemented through `ComputerActionService`, when the optional `computer-uia` dependency is installed (DEC-046; Batch 01 Milestones 1-3, Batch 02 Milestone 0, Batch 03 Milestones 0/2 of Phase 18 Workstream A). `invoke`/`toggle`/`select` are now **all three** physically proven live on NIGHTFURY through a JARVIS-owned native Win32 fixture (`scripts/phase18/uia_fixture_host.py`, replacing the Batch 02 Edge Guest fixture which never reached Chromium content within the adapter's `MAX_INSPECT_DEPTH=5` bound) - 3/3 clean runs each, re-confirmed in both Batch 03 Milestone 0 and Milestone 2, with independent evidence each time. Batch 02 Milestone 0 hardened targeting (strong/weak identity, `list_windows` privacy filtering, fresh post-action re-observation, target-aware approval preview, disabled/offscreen/password fail-closed checks); Batch 03 Milestone 0 generalized that same trusted-preview/binding mechanism beyond semantic actions to `computer.pointer.act` and window-targeted keyboard actions, bounding approval expiry by the *actual* configured reference TTL rather than a hardcoded constant; Batch 04 Milestone 1 extended it again to a genuine dual-target binding for `drag_element_to_element`. See `docs/audits/PHASE_18_WORKSTREAM_A_BATCH_04.md`. No generic text/value write (`set_value`), no OCR/visual fallback, no multi-app recovery loop - see GAP-0102 through GAP-0106. |
| Computer Use V2 evaluation suite | `PARTIAL` | deterministic `computer_use_v2` suite (`src/jarvis/evaluation/computer_use_v2.py`, 53 cases after Batch 08) is registered through the existing `EvaluationService`, has no GUI dependency, and passes its current deterministic checks. Batch 09 adds an explicitly opt-in, finite owner-session runner boundary; `RW-CALC-001` is physically PASS 3/3 with exact semantic grounding and independent readback. Brave host focus remains unproven because the current desktop exposes multiple inactive exact Brave windows, and authenticated web control remains a Browser V2 blocker. The broader real-app/failure-mode breadth remains in GAP-0105. |
| Local visual OCR grounding | `PARTIAL` | `computer.visual.read` provides bounded offline EasyOCR OCR through opaque `window_ref`/`element_ref` inputs; `computer.visual.act` adds one bounded OCR-grounded left-click through the existing approval/native-input path. Raw pixels, geometry, and refs remain transient/opaque, the visual reference TTL is 30 seconds, and element-origin visual refs remain denied in favor of semantic UIA targeting. Batch 09 T0 physically proves A/B/C/D/E 3/3 with zero network and exact cleanup; T1 owner-session acceptance remains configuration-gated. |
| Approved-root file access and project workflows | `PARTIAL` bounded | `FileAccessPolicy` (`src/jarvis/computer/file_access.py`, Batch 03 Milestone 1, hardened Batch 04/05) confines reads and the approval-gated `computer.files.manage` create/replace/copy/move/rename/recycle operations to explicit owner-configured roots, fail-closed when unconfigured; component-wise containment, junction/`..` resistance, sensitive-path denial, final-reparse denial, bounded atomic writes, exclusive copies, and independent post-state verification are covered by current tests. File dialogs, cross-window file drag/drop, and owner-file/real-app acceptance remain open under GAP-0503/GAP-0102. |
| On-demand screen capture | `IMPLEMENTED` bounded | native Windows GDI transient capture exists |
| Visual actuation | `PARTIAL` | bounded `computer.visual.act` exists behind the canonical approval/native-input path; Batch 09 T0 proves the owned visual happy path and refusal/uncertainty safeguards 3/3, while broader real-app visual use remains configuration-gated |
| Camera | `PLANNED/OPTIONAL` | architecture-only; continuous camera capture is off |
| Robust multi-app Computer Use V2 | `PLANNED` | native app registry is the preferred surface, but broad per-application semantic workflows and Tier A/B physical evidence remain open |

**Batch 08 M0 OCR truth:** the evaluation-only runner now uses sequence-aware
NFKC/whitespace-normalized Levenshtein similarity. Corrected three-run A/B/C
physical measurements through the owned OCR fixture left production routing
unchanged: Candidate C failed the required English-similarity and warm
two-pass gates (`OCR_BOUNDED_TWO_PASS_EVALUATION_NO_CHANGE`). DEC-048 remains
accepted. Batch 08 M1 added bounded OCR-grounded visual left-click through the
existing approval and native-input authorities. M2 physically proved
stale-target refusal, duplicate-target ambiguity refusal, approval-target
drift refusal, and post-input uncertainty handling 3/3 each, but the live
happy-path click/status gate remains `PHYSICAL_PENDING` because the CPU-only
host's OCR/revalidation sequence expires the visual reference before
foreground-safe input can begin. No automatic retry or focus-policy bypass
was added; see `docs/audits/PHASE_18_WORKSTREAM_A_BATCH_08.md`.

### Native desktop application addendum — 2026-09-19

`5a0ea52` carries the bounded `InstalledApplicationRegistry` and wires it through
the existing Computer Use authority. Discovery is limited to standard Start
Menu roots, Windows App Paths, and explicit known-app fallbacks. The UI now
exposes installed applications and owner-controlled `AUTO`/`DESKTOP`/
`BROWSER`/`API` surface preferences without exposing private launch identity.
The default `AUTO` resolution is native desktop for a verified launchable
non-denied app; browser/API preferences remain explicit selections and do not
claim that their provider is configured.

The bounded host discovery observed 162 catalog entries on the inspected
Windows machine. Deterministic registry and boundary tests pass, and the
frontend tests/build pass. A canonical physical Notepad probe launched the
verified target and observed its window, but the non-interactive runner could
not verify foreground ownership (`application_focus_not_verified`); cleanup
used the canonical safe-process path. This is `PARTIAL`/launch-only evidence,
not Tier A/B acceptance. No arbitrary executable path, shell, remote-phone
launch, credential, cookie, or normal Brave profile path was introduced.

### T06 owner-session preflight — 2026-09-19

The finite Browser V2 owner runner was then exercised with the existing local
owner/device identity derived only in process memory, the exact standard Brave
binary, the dedicated JARVIS `OwnerPersistent` profile, and send confirmation
disabled. It reached `https://chatgpt.com/` and returned
`BROWSER_V2_PARTIAL` / `authenticated_shell_uncertain`. No credentials were
entered, no nonce was sent, no raw screenshot or secret was persisted, and all
security counters remained zero. This proves bounded target/profile
preflight, not authenticated web acceptance; manual owner authentication and
an explicit send confirmation remain required.

### Browser/research/MCP/skills

| Capability | Status | Current truth |
|---|---|---|
| Bounded HTTP/HTML browser reads | `IMPLEMENTED` | URL sessions, bounded HTML/text/links/headings/find/back metadata |
| Browser URL/SSRF/redirect safety | `IMPLEMENTED` | hardened Phase 15 |
| Browser model-facing read path | `IMPLEMENTED` | Phase 15 closure |
| Live Playwright navigation/read foundation | `IMPLEMENTED` (optional) | `PlaywrightBrowserController` is lazy and subordinate to `BrowserActionService`; exact configured Brave executable and optional dependency are required, while default runtime remains Local/offline |
| Live Playwright click/type/select | `IMPLEMENTED` (optional) | T3 opaque refs, actionability, approval binding, exactly-once behavior, and independent verification are covered by deterministic tests; physical owner/authenticated acceptance remains pending |
| Browser session/profile policy | `IMPLEMENTED` | default isolated ephemeral contexts plus explicit owner-persistent dedicated JARVIS profile; normal Brave/Chrome/Edge profiles rejected (DEC-049, Batch 10 T2) |
| Browser upload/download/screenshots | `IMPLEMENTED` (optional Playwright) | downloads require an explicit `FileAccessPolicy` root and verify final size/SHA-256 after bounded, policy-checked redirects; uploads require a sensitive-path-safe approved file and opaque file-input approval binding; screenshots are on-demand, opaque-ref, in-memory transient only. Local/default runtime remains fail-closed; live owner-authenticated acceptance remains pending. |
| Research evidence/provenance | `IMPLEMENTED` | local-first ResearchService/evidence ledger exists |
| Advanced static main-content extraction | `IMPLEMENTED` bounded | Local static parser now prefers bounded visible `<main>` text, headings, safe links/metadata, and provenance; heavier third-party main-content parsers remain optional |
| Dynamic authenticated extraction | `PARTIAL` optional | Playwright dynamic DOM extraction returns bounded provenance-aware content; broader research-provider integration and owner-authenticated acceptance remain pending |
| MCP governed foundation | `IMPLEMENTED` | Phase 15 final pass; schemas bounded/sanitized |
| MCP-backed reviewed workspace skill | `IMPLEMENTED` | Phase 15 closure |
| External MCP servers | `NOT_CONFIGURED` unless explicitly configured | no arbitrary external internet MCP authority |
| Skills registry/policy/executor | `IMPLEMENTED` | trust states/progressive loading foundations exist |

### Developer/workspace

| Capability | Status | Current truth |
|---|---|---|
| Workspace intelligence/context | `IMPLEMENTED` foundation | scoped local workspace metadata/intelligence exists |
| Read-only workspace skill | `IMPLEMENTED` | bounded Phase 15 path |
| Developer/engineering service seams | `IMPLEMENTED` foundation | typed providers/gateway exist |
| Live external developer worker | `PARTIAL` | installed Codex is discovered by default but the bounded read-only, workspace-scoped adapter activates only with `JARVIS_CODEX_WORKER_ENABLED=true`; ephemeral execution, output redaction, and no write mode are implemented, while live authentication/provider availability and independent postcondition verification remain owner/deployment gates |
| Full safe repository/Jupyter workflows | `PLANNED` | must remain capability-scoped and approval/audit bound |

### Communications and daily operations

| Capability | Status | Current truth |
|---|---|---|
| CommunicationsHub | `IMPLEMENTED` foundation | list/sync/read/search/draft/send contract exists |
| Local deterministic communication channel | `IMPLEMENTED` | default runtime uses local in-memory channel |
| Live email provider | `PLANNED` | deferred pending explicit provider/credential path |
| Telegram/Discord providers | `PLANNED/OPTIONAL` | adapter candidates only |
| Calendar provider | `PLANNED` | no current repository capability was found in review |
| Reminders/routines/briefings | `IMPLEMENTED` foundations | automation/briefing/intelligence services exist; personal live workflows still need productization |

### Voice

| Capability | Status | Current truth |
|---|---|---|
| VoiceCore | `IMPLEMENTED` | one canonical VoiceCore |
| Wake/VAD/STT/TTS pipeline | `IMPLEMENTED` code | local stack built in Phase 13 |
| Zero-touch desktop voice productization | `IMPLEMENTED` code | setup/settings/startup path exists |
| Physical microphone capture | `IMPLEMENTED` / physically proven | owner mic signal proof recorded |
| Full English/Egyptian Arabic/mixed physical voice | `PHYSICAL_PENDING` | not fully accepted |
| Egyptian-accent TTS quality | `PHYSICAL_PENDING` / weak current asset | current Arabic voice is not proven Egyptian quality |
| Follow-up/barge-in/Bluetooth duplex/device-loss recovery | `PHYSICAL_PENDING` | backlog for final acceptance |
| Speaker verification | `PLANNED/OPTIONAL` | explicitly deferred; do not claim it exists |
| Multi-room voice | code/protocol `PARTIAL`; physical `PHYSICAL_PENDING` | same VoiceCore rule preserved |

### Devices/home/distributed runtime

| Capability | Status | Current truth |
|---|---|---|
| Device fabric/enrollment/revocation | `IMPLEMENTED` | current Phase 17 audit pass |
| Authenticated LAN node transport | `IMPLEMENTED` code | explicit bounded trust policy; physical scenarios still separate |
| Non-RFC1918 owner LAN override | `IMPLEMENTED` | explicit local CIDR only; not hardcoded |
| Desktop zero-touch node-server startup | `IMPLEMENTED` code | current Phase 17 closure |
| VENOM daemon/provisioning code | `IMPLEMENTED` | real venv/local package/import-smoke path in closure |
| Physical VENOM deployment | `BLOCKED`/`PHYSICAL_PENDING` | authentication/deployment gate not completed |
| HomeActionService | `IMPLEMENTED` foundation | canonical approval path exists |
| Home Assistant live integration | `NOT_CONFIGURED` | no physical live acceptance |
| MQTT live broker | `NOT_CONFIGURED` | no false success when absent |
| ESP32 physical fabric | `PHYSICAL_PENDING` | not run |
| Room endpoint fabric | `IMPLEMENTED` code foundation | physical room/acoustic acceptance pending |
| Phone/mobile endpoint | `PLANNED` | cross-device model exists; no verified phone client is claimed |

### Product UI / production engineering

| Capability | Status | Current truth |
|---|---|---|
| React/TypeScript/Vite Command Center | `IMPLEMENTED` | Phase 14 final pass |
| Backend-truth projection | `IMPLEMENTED` principle | UI is non-authoritative |
| Setup/repair/diagnostic native desktop shell | `IMPLEMENTED` foundation | retained for operational functions |
| Tony-Stark-style future capability/UX mapping from new screenshots | `PLANNED` | awaiting owner screenshots; must not fake capabilities |
| CI/required status checks | `PARTIAL` | `.github/workflows/ci.yml` is committed and hosted run `35355436554` at `71157dd` is green for Python tests/compile and frontend tests/build/high-severity audit; required-check branch protection remains pending |
| Branch protection/signing governance | `PLANNED` | governance hardening belongs to Phase 18 |
| Watchdog/recovery/performance regression/security hardening | `PLANNED/PARTIAL` | production foundations exist; Phase 18 finalization pending |
| Final physical E2E release acceptance | `PLANNED` | Phase 19 |

## 4. Current hardware assumptions

### NIGHTFURY
Recorded current host:
- Windows 11;
- Intel Core i7-12700H;
- ~16 GB RAM;
- NVIDIA RTX 4050 Laptop GPU;
- ~6 GB VRAM.

Current local-model evidence includes a verified llama.cpp CUDA runtime and an existing ~5.5 GB Qwen GGUF loaded in place. Exact future model choice remains benchmark-selected, not architecture-locked.

### VENOM
Recorded role:
- older Lenovo G450-class machine;
- Ubuntu Server;
- low RAM/no useful AI GPU;
- lightweight always-on infrastructure node only.

Do not move heavy inference or central authority to VENOM.

## 5. Known physical truth

Do not inflate these states:
- local brain: proven;
- Command Center: code/product pass;
- microphone capture: proven good;
- full voice: pending;
- VENOM reachable/manual SSH: historically proven;
- automated VENOM deployment: not completed;
- Home Assistant physical: not configured;
- MQTT physical: not configured;
- ESP32 physical: not run;
- room voice physical: not run.
- Batch 09 T2: `RW-CALC-001` is physically `PASS` 3/3 with independent
  Calculator readback; Brave provenance is recorded, but host open/focus is
  `PARTIAL` because the current desktop has multiple inactive exact Brave
  windows. Brave navigation/authentication is a `CROSS_WORKSTREAM_BLOCKER`
  until the approved Browser V2 adapter exists.
- Native installed-app control: bounded catalog and exact native launch/focus
  code are present, but the current generic-app physical probe is
  `LAUNCH_ONLY`; focus verification failed closed and no Tier A/B status is
  claimed.

## 6. Evidence references

Primary current repository evidence:
- `docs/audits/MEGA_PHASE_17_REVIEW.md`
- `docs/phase17/PHASE17_ACCEPTANCE.md`
- `docs/architecture/COMPUTER_CONTROL.md`
- `docs/architecture/GROUNDED_DESKTOP_INTERACTION.md`
- `docs/architecture/BROWSER_AUTOMATION.md`
- `docs/architecture/VISUAL_PERCEPTION.md`
- `docs/architecture/COMMUNICATIONS_HUB.md`
- `docs/architecture/AUTOMATION.md`
- `docs/audits/MEGA_PHASE_16_REVIEW.md`
- `docs/deferred/PHASE13_PHYSICAL_ACCEPTANCE_BACKLOG.md`

## 7. Final release closure truth — 2026-09-18

The feature branch remains a desktop release candidate, not a universal live
integration PASS. Code acceptance and hosted CI are green at `71157dd`; the
current local product launches through the existing
Start Menu shortcut, owns one instance, serves the Command Center locally,
and exposes truthful degraded/not-configured states for voice, browser
authentication, automations, approvals, and external integrations.

The public Browser V2 proof is independent of ChatGPT and uses the exact
installed signed Brave executable with a dedicated JARVIS profile. ChatGPT web
remains service-surface blocked by the observed 403/empty shell, and the
installed OpenAI desktop package was verified as Codex rather than ChatGPT.
Owner-session opt-in, exact service destinations, manual authentication,
physical voice, safe-paste foreground proof, and clean cold shutdown remain
open gates. See the current completion audit for the evidence matrix.
