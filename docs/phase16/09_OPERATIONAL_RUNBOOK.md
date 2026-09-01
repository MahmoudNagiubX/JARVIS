# Phase 16: Operational Runbook

## 1. Routine Maintenance Operations

### Memory Expiry & Archive Maintenance
`DurableMemoryService.maintain(owner_id)` scans active memory records:
- Records with `valid_until <= now` transition to `status="expired"`.
- Records with `retention_policy="temporary"` and `pinned=False` transition to `archived=1`.
- Can be scheduled as a background maintenance cron or run at startup.

### World State Expiry
`DurableWorldStateService.expire(owner_id)` scans world facts:
- Facts exceeding their `freshness_seconds` TTL transition to `conflict_state="expired"`.
- Emits `world_state.expired` event.

### Proactive Detection Scan
`DurableProactiveService.detect(owner_id)` runs deterministic rule scans:
- Evaluates build, tests, deadlines, goals, disk space, dev server status.
- Deduplicates using fingerprint hashes within cooldown windows.

## 2. Emergency Procedures

### Forgetting Compromised or Sensitive Categories
To erase all memories in a given category:
```bash
POST /memory/forget-category
{"category": "sensitive_project"}
```

### Resetting Stuck Missions
If a mission hangs or requires emergency termination:
```bash
POST /missions/{mission_id}/cancel
```
The mission transitions cleanly to `CANCELLED` and releases any acquired resources.

### Reconciling Crashed Runtime Runs
On startup, `JarvisRuntime.start()` automatically invokes:
1. `RuntimeRepository.reconcile_active_runs()`
2. `RuntimeRepository.reconcile_missions()`
3. `RuntimeRepository.reconcile_research_runs()`
Any hanging runs from prior crashes are marked `FAILED` with `error_code="process_restarted"`.
