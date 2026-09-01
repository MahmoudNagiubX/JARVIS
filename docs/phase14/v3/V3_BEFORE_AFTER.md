# Phase 14 V3 before/after

| Before | After |
|---|---|
| Home used a large, dominant reactor composition that competed with the owner artwork. | Home uses the owner wallpaper as the scene and a restrained reactor/core accent. |
| Visual state was distributed across screen markup and legacy visual wrappers. | `deriveVisualState()` provides one pure presentation projection and the new cinematic/holographic primitives consume it. |
| Tactical presentation mixed decorative geometry with generic wrappers. | Radar, compass, arcs, scan plane, rings, and node links are product-owned SVG/CSS primitives with real counts and labels. |
| Shell navigation and live context were fixed-width presentation surfaces. | Both docks have accessible collapse controls and responsive behavior while preserving the router and context data. |
| Donor inspiration was recorded mainly at V2 level. | V3 records exact donor source paths, extraction decisions, exclusions, visual rules, and review limitations. |
| A duplicate desktop launch stopped after `already_running`. | The first instance publishes only its local app URL in the existing lock; a duplicate launch reopens that URL without starting another runtime. |

The change is deliberately a presentation and bounded lifecycle closure. It does
not add a scheduler, EventBus, VoiceCore, persistence store, browser runtime,
WebGL loop, cloud dependency, or second API authority.
