# JARVIS UI Gap Register

| ID | Severity | Surface | Frontend | Backend | Symptom | Root cause | Fix | Test / evidence | Status |
|---|---:|---|---|---|---|---|---|---|---|
| UI-001 | P1 | IA | many top-level nav groups | capabilities already have typed services | product feels fragmented | route structure mirrors implementation history | five-area shell with compatibility redirects | route tests + live shell render | CLOSED |
| UI-002 | P1 | Native action | chat always starts a normal run | `AgentRuntime` had no deterministic app-open branch | simple app opens waited for model reasoning | bounded server-side fast path | Python no-model-call test + live Calculator/Notion receipts | CLOSED |
| UI-003 | P0 | Authority | risk if frontend attempted native shortcut | backend authorities exist | frontend could become tempting bypass | keep classifier/server/runtime-only | security tests + source audit | CLOSED BY DESIGN |
| UI-004 | P2 | Command | Home showed equal-weight telemetry/cards | projection is real but presentation was noisy | weak NOW/attention hierarchy | calmer Command hierarchy with restrained wallpaper treatment | rendered review at four viewports | CLOSED |
| UI-005 | P2 | Shell | Unicode glyphs and mixed HUD primitives | no backend defect | icon migration is incomplete | retain semantic labels and track bounded icon cleanup | route/a11y tests; no capability loss | PARTIAL P2 |
| UI-006 | P1 | Converse | result detail was mostly text/debug | run/tool endpoints expose structured data | verification/approval states were easy to miss | structured tool/result surfaces and truthful pending copy | live chat/native receipts + frontend tests | CLOSED |
| UI-007 | P2 | Bidi | message direction was not a first-class display rule | backend preserves content | Arabic/mixed technical strings can read poorly | preserve Arabic command path and localized message rendering | live `افتح Notion` + UI regression coverage | CLOSED |
| UI-008 | P2 | Motion | multiple cinematic surfaces could animate together | no backend defect | unnecessary paint/CPU risk | bounded Core motion and reduced-motion CSS | CSS reduced-motion rules + frontend suite | CLOSED |
| UI-009 | P1 | Session | stale/expired session errors could look technical | session fix is already in baseline | raw codes could leak into product copy | human copy with diagnostic inspector detail | fresh packaged desktop session + refresh persistence | CLOSED |
| UI-010 | P1 | Truth | accepted/attempted actions could look complete | typed results include `verified` | delivery and verification conflated | explicit Verified/Unverified/Failed states | live verified native receipts | CLOSED |
| UI-011 | P2 | Work | browser/research/engineering/devices lacked one shared workspace | services are separate but canonical | navigation cost and duplicate layout | Work hub with compatibility links and shared product copy | route tests + build/render review | CLOSED |
| UI-012 | P2 | System | runtime/provider details were scattered | `/experience/system` and health exist | technical detail competed with command | System utility with progressive disclosure | live System page + API matrix | CLOSED |
| UI-013 | P0 | Session/runtime | baseline browser and local runtime fixes must not regress | already fixed in `4ce6291`/`f3e6575` | refactor could reintroduce failure | preserve and rerun current closure tests | full regression + live browser | CLOSED BY REGRESSION GATE |

## Closure rule

No capability is removed by this register. A row moves to CLOSED only with a test or live artifact linked to the new canonical home. P0/P1 rows must be closed before the final product-ready verdict.
