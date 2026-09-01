# Phase 16: Authoritative World State & Freshness TTL Boundary

## 1. System Role & Separation
`DurableWorldStateService` is the authority for real-time, transient operational facts about the local environment (open editors, git branches, running processes, device telemetry, battery levels, network connectivity).

### Critical Firewall Boundary
World State observations and facts represent transient state. They are **never** automatically inserted or mirrored into the durable `memories` table. Only deliberate knowledge accepted by `DurableMemoryService` persists across long-term memory.

## 2. Observation Lifecycle & Freshness TTL

Every observation ingested by the runtime includes a `freshness_seconds` duration or explicit `expires_at` timestamp.

```
Observation Ingested (e.g. freshness_seconds = 60s)
          |
          v
   Fact Fusion in World State
          |
          +---> Active Turn Queries (observed_at + freshness > now) -> Included in Context
          |
          +---> Expired Observations (observed_at + freshness <= now) -> Excluded from Context
          |
          +---> Scheduled Maintenance: expire() -> conflict_state = "expired"
```

## 3. Fact Conflict Resolution

When competing observations report conflicting values for the same key (e.g. different sources reporting different git branches):
1. Both observations are recorded in the `world_observations` table with full provenance.
2. The latest observation with the highest source priority is surfaced in the active snapshot.
3. A `WorldStateConflict` record is generated and emitted via the event bus for inspection.
4. If one observation expires, the active fact reverts to the latest valid unexpired observation.
