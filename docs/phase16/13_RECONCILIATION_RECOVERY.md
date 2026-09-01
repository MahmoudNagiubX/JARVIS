# Phase 16: Reconciliation & Process Crash Recovery

## 1. Crash & Restart Failure Modes
When the JARVIS process terminates abruptly (SIGKILL, power failure, system restart):
1. In-flight agent turns remain in `running` status.
2. In-flight missions remain in `running` or `waiting` status.
3. In-flight research tasks remain in `running` status.
4. SQLite WAL journal remains consistent and recovers cleanly on next connection.

## 2. Boot-time Reconciliation Pipeline

During `JarvisRuntime.start()`, before accepting any external requests, the runtime executes:

```python
# 1. Reconcile Agent Runs
reconciled_runs = self.repository.reconcile_active_runs()

# 2. Reconcile Missions
reconciled_missions = self.repository.reconcile_missions()

# 3. Reconcile Research Runs
reconciled_research = self.repository.reconcile_research_runs()

# 4. Emit System Recovery Event
if reconciled_runs or reconciled_missions or reconciled_research:
    recovery = Event.create(
        "system.runtime.reconciled", EventCategory.SYSTEM,
        correlation_id=self.runtime_id, state=EventState.COMPLETED,
        payload={
            "reconciled_runs": reconciled_runs,
            "reconciled_missions": reconciled_missions,
            "reconciled_research": reconciled_research,
        },
    )
    self.repository.append_event(recovery)
    await self.event_bus.publish(recovery)
```

## 3. Reconciled State Guarantees
- Interrupted missions transition to `status="failed"` with `result={"error_code": "process_restarted"}`.
- Interrupted research jobs transition to `status="failed"`.
- No orphan locks or zombie processes remain.
- The owner is notified of interrupted missions on next command center session.
