# JARVIS Mega Phase 16: Personal Intelligence Architecture Overview

## 1. System Architecture

Phase 16 enhances and activates the product-owned Personal Intelligence stack within the existing canonical JARVIS authority model. No secondary schedulers, parallel event buses, second runtimes, or ungrounded cognitive agents are introduced.

```
+-----------------------------------------------------------------------------------+
|                                  JARVIS CORE RUNTIME                               |
|                                                                                   |
|  +------------------------+  +------------------------+  +---------------------+  |
|  |  DurableMemoryService  |  | DurableWorldStateServ. |  | DurableGoalEngine   |  |
|  |  - Candidate Extractor |  |  - Fact Fusion Engine  |  |  - Goal State Mach. |  |
|  |  - Policy Firewall     |  |  - Freshness TTL Watch |  |  - Checkpoints/Prog |  |
|  |  - Keyword / Retriever |  |  - Conflict Detector   |  |  - Priority Bounds  |  |
|  +-----------+------------+  +-----------+------------+  +----------+----------+  |
|              |                           |                          |             |
|              +-------------+-------------+--------------------------+             |
|                            |                                                      |
|                            v                                                      |
|              +---------------------------+                                        |
|              |     ContextAssembler      | <--- ActiveDesktopContextService       |
|              |  - Priority Hierarchy     | <--- ToolRegistry                      |
|              |  - Hard Budget Enforcement| <--- OfflineModeService                |
|              |  - Debug Metadata Trace   |                                        |
|              +-------------+-------------+                                        |
|                            |                                                      |
|                            v                                                      |
|              +---------------------------+                                        |
|              |       AgentRuntime        |                                        |
|              |    (Turn Execution Core)  |                                        |
|              +-------------+-------------+                                        |
|                            |                                                      |
|                            v                                                      |
|  +------------------------+  +------------------------+  +---------------------+  |
|  |     MissionService     |  | DurableProactiveServ.  |  |  AutomationService  |  |
|  |  - Step Planner        |  |  - Deterministic Scans |  |  - Event Subscript. |  |
|  |  - Budget Guardrails   |  |  - Fingerprint Cooldown|  |  - Schedule Rules   |  |
|  |  - Approval Pause/Res. |  |  - Safe Action Exec.   |  |  - Safe Dispatches  |  |
|  +------------------------+  +------------------------+  +---------------------+  |
|                                                                                   |
|  +-----------------------------------------------------------------------------+  |
|  |              RuntimeRepository (SQLite WAL Persistent Storage)              |  |
|  |  [memories] [world_facts] [world_observations] [goals] [missions] [findings] |  |
|  +-----------------------------------------------------------------------------+  |
+-----------------------------------------------------------------------------------+
```

## 2. Component Responsibilities

### DurableMemoryService (`src/jarvis/memory/`)
- Accepts explicit owner statements, preferences, project facts, tasks, and profile data.
- Enforces strict policy: blocks API keys, bearer tokens, passwords, private keys, session cookies, and prompt injections from untrusted sources (e.g. web search, browser scrapers).
- Detects structured key collisions and marks previous records as superseded.
- Executes keyword retrieval with Arabic and English text normalization and diacritics stripping.

### DurableWorldStateService (`src/jarvis/world_state/`)
- Ingests short-lived, transient observations from workspace watchers, system metrics, hardware status, and git state.
- Strictly bounds observations with time-to-live (`freshness_seconds`).
- Maintains a clean separation firewall: transient facts never pollute the durable `memories` table.

### ContextAssembler (`src/jarvis/context/`)
- Assembles an inspectable, bounded context snapshot for each model turn.
- Strictly adheres to the priority hierarchy: Authority Policy -> Owner Request -> Fresh World State -> Active Goals/Missions -> Accepted Relevant Memories -> Desktop Context -> Personalization.
- Emits transparent debug selection metadata (`selected_memory_ids`, `selected_memory_count`, `memory_byte_estimate`, `selected_world_facts`, `active_goal_ids`, `active_finding_ids`).

### DurableGoalEngine & MissionService (`src/jarvis/goals/`, `src/jarvis/missions/`)
- Manages user-directed long-term goals and short-term execution plans.
- Bounded mission execution under `MissionBudget` limits (max steps, tool calls, duration, replans).
- Consequential steps pause execution for owner approval via `DurableApprovalEngine`.
- Interrupted runs reconcile automatically on runtime reboot.

### DurableProactiveService & AutomationService (`src/jarvis/proactive/`, `src/jarvis/automation/`)
- Scans authoritative runtime state using 9 deterministic detectors.
- Emits deduplicated findings with cooldown windows preventing repeated notifications.
- Automations execute safe registered services (`skill`, `mission`, `notification`, `briefing`) without executing raw shell commands.
