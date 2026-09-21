# JARVIS Native Action Latency

## Measurement contract

Latency is measured from real `AgentRuntime` execution using `time.monotonic_ns()` at these boundaries:

| Field | Boundary |
|---|---|
| `request_received` | authenticated `AgentRuntime` fast-path entry after owner/device binding |
| `intent_classified` | narrow grammar accepted or declined |
| `app_ref_resolved` | `InstalledApplicationRegistry.find()` returned one verified application and opaque `app_ref` |
| `authority_decided` | `ToolExecutionService` completed permission/approval decision boundary |
| `launch_dispatched` | canonical `ComputerActionService` native adapter initiated launch/focus |
| `verification_completed` | application window/process readback returned verified/unverified outcome |

The payload stores bounded millisecond deltas and a `verification_state`; it never stores raw command secrets, executable paths, or untrusted model text.

## Budgets

These are targets, not guarantees about Windows or third-party application startup:

- UI accepted state: under 150ms after backend acceptance.
- Deterministic classification and registry resolution: under 250ms CPU-side on a warm indexed registry.
- Native dispatch initiation: under 500ms after acceptance where Windows permits.
- Verification is reported separately and may exceed launch dispatch time.

## Required outcome language

| Evidence | Product copy |
|---|---|
| accepted and currently launching | `Opening {app}…` |
| independent window/process readback verified | `{app} opened.` + `Verified` |
| launch attempted but readback unavailable | `Launch sent.` + `Completed · Unverified` |
| bounded launch/readback failure | `{app} did not open.` |
| ambiguous/not installed | `I couldn't find one clear installed app named {query}.` |

## Fast-path scope

Accepted grammar is deliberately narrow: `Open`, `Launch`, `Start`, `افتح`, and `شغل` followed by one bounded app-name phrase. Compound commands, URLs, paths, conjunctions, unsupported verbs, and ambiguous matches fall back to normal AgentRuntime/model routing.

The path remains authenticated and canonical:

```text
HTTP session
→ AgentRuntime run
→ deterministic classifier
→ InstalledApplicationRegistry opaque app_ref
→ ToolExecutionService
→ Permission/Autonomy/Risk
→ ComputerActionService
→ native adapter
→ process/window verification
→ audit/event/result
```

## Evidence table

Live observations are recorded only after the product interpreter runs the path. The table is intentionally evidence-backed rather than filled with estimates.

| Command | Installed target | Fast-path used | Model call | Dispatch ms | Verification ms | Result |
|---|---|---:|---:|---:|---:|---|
| `Open Calculator` | `Calculator` (`app-fa7b344e2f19669d1eefab1e`) | yes | no (`model_id=null`) | 7628.199 | 9298.666 | verified |
| `Open Notion` | `Notion` (`app-373e2a20fda6346cd37ba9aa`) | yes | no (`model_id=null`) | 788.091 | 3088.571 | verified |
| `افتح Notion` | `Notion` (`app-373e2a20fda6346cd37ba9aa`) | yes | no (`model_id=null`) | 858.657 | 3576.836 | verified |

## Receipt detail

These are real monotonic receipts emitted by the packaged desktop interpreter on 2026-09-21, not benchmark fixtures. `request_received` is the zero baseline for each run. The cold Calculator registry refresh accounts for its larger `app_ref_resolved` value; the warm Notion receipts show the expected low overhead.

| Command | intent classified | app ref resolved | authority decided | launch dispatched | verification completed |
|---|---:|---:|---:|---:|---:|
| `Open Calculator` | 284.594 ms | 6538.834 ms | 7311.276 ms | 7628.199 ms | 9298.666 ms |
| `Open Notion` | 39.681 ms | 42.311 ms | 163.709 ms | 788.091 ms | 3088.571 ms |
| `افتح Notion` | 34.798 ms | 37.418 ms | 156.731 ms | 858.657 ms | 3576.836 ms |

The verification interval includes Windows process/window startup and focus handoff; third-party startup is not attributed to JARVIS overhead. The first pre-fix foreground-lock failure is retained as a regression note, not counted as a passing result.
