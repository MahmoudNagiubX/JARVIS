# JARVIS UI Gap Register

| ID | Severity | Surface | Frontend | Backend | Symptom | Root cause | Fix | Test / evidence | Status |
|---|---:|---|---|---|---|---|---|---|---|
| UI-001 | P1 | IA | many top-level nav groups | capabilities already have typed services | product feels fragmented | route structure mirrors implementation history | five-area shell with compatibility redirects | route tests + live navigation | OPEN |
| UI-002 | P1 | Native action | chat always starts a normal run | `AgentRuntime` has no deterministic app-open branch | simple app opens wait for model reasoning | bounded server-side fast path | no-model-call integration test | OPEN |
| UI-003 | P0 | Authority | risk if frontend attempted native shortcut | backend authorities exist | frontend could become tempting bypass | keep classifier/server/runtime-only | security tests + source audit | CLOSED BY DESIGN |
| UI-004 | P2 | Command | Home shows equal-weight telemetry/cards | projection is real but presentation is noisy | weak NOW/attention hierarchy | redesign Command around NOW, NEEDS YOU, CONTINUE, SYSTEM | rendered review + component tests | OPEN |
| UI-005 | P2 | Shell | Unicode glyphs and mixed HUD primitives | no backend defect | inconsistent iconography and accessibility | adopt bounded Lucide masks and semantic labels | accessibility tests | OPEN |
| UI-006 | P1 | Converse | result detail is mostly text/debug | run/tool endpoints already expose structured data | verification/approval states are easy to miss | structured message blocks + inspector | chat/approval tests | OPEN |
| UI-007 | P2 | Bidi | message direction is not a first-class display rule | backend preserves content | Arabic/mixed technical strings can read poorly | direction detection with LTR technical spans | bilingual frontend tests + rendered review | OPEN |
| UI-008 | P2 | Motion | multiple cinematic surfaces can animate together | no backend defect | unnecessary paint/CPU risk | one semantic Core loop, explicit transitions, reduced motion | CSS inspection + reduced-motion tests | OPEN |
| UI-009 | P1 | Session | stale/expired session errors can look technical | session fix is already in baseline | raw codes can leak into product copy | human copy with diagnostic inspector detail | session regression + UI test | PARTIAL |
| UI-010 | P1 | Truth | accepted/attempted actions can look complete | typed results include `verified` | delivery and verification conflated | explicit Verified/Unverified/Failed states | native action integration test | OPEN |
| UI-011 | P2 | Work | browser/research/engineering/devices lack one shared workspace | services are separate but canonical | navigation cost and duplicate layout | Work segmented modes and shared inspector | route/endpoint matrix | OPEN |
| UI-012 | P2 | System | runtime/provider details are scattered | `/experience/system` and health exist | technical detail competes with command | System utility with progressive disclosure | system screen tests | OPEN |
| UI-013 | P0 | Session/runtime | baseline browser and local runtime fixes must not regress | already fixed in `4ce6291`/`f3e6575` | refactor could reintroduce failure | preserve and rerun current closure tests | full regression + live browser | CLOSED BY REGRESSION GATE |

## Closure rule

No capability is removed by this register. A row moves to CLOSED only with a test or live artifact linked to the new canonical home. P0/P1 rows must be closed before the final product-ready verdict.
