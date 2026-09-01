# Phase 16: Goal & Mission Orchestration

## 1. Goal State Machine (`DurableGoalEngine`)

Goals represent user-directed objectives that persist across runtime restarts and multiple turns.

```
       +--------+
       | DRAFT  |
       +----+---+
            |
            v
       +----+---+       pause()       +--------+
       | ACTIVE | <=================> | PAUSED |
       +----+---+       resume()      +--------+
            |
            +------------+------------+
            |                         |
            v                         v
     +------+------+           +------+------+
     |  COMPLETED  |           |  CANCELLED  |
     +-------------+           +-------------+
```

### Goal Operations
- `create(goal)`: Registers proposed/draft goal.
- `activate(goal_id)`: Transitions to `active`.
- `checkpoint(goal_id, title, evidence)`: Records progress milestones with evidence.
- `pause(goal_id)` / `resume(goal_id)`: Suspends and resumes goal tracking.
- `complete(goal_id)` / `cancel(goal_id)`: Concludes goal lifecycle.

## 2. Mission Service & Execution Guardrails (`MissionService`)

Missions break goals into discrete executable steps governed by strict resource budgets.

### MissionBudget Enforcement
```python
@dataclass(frozen=True, slots=True)
class MissionBudget:
    max_steps: int = 10
    max_tool_calls: int = 25
    max_duration: float = 600.0
    max_worker_runs: int = 5
    max_external_actions: int = 5
    max_replans: int = 3
```

Any mission execution exceeding its configured budget immediately raises a budget exhaustion error and transitions to `FAILED`.

## 3. Consequential Actions & Approval Pause

When a mission step involves a consequential or irreversible action (e.g. modifying workspace files, deploying services, making external API mutations):
1. `MissionService.advance()` marks the step as requiring approval.
2. A formal `ApprovalRequest` is submitted to `DurableApprovalEngine`.
3. The mission status transitions to `WAITING_APPROVAL` with `approval_id` assigned.
4. The mission pauses and does NOT execute the step.
5. Upon user review:
   - If approved: `MissionService.resume(owner_id, mission_id)` transitions to `RUNNING` and executes the step.
   - If rejected: `MissionService.resume(owner_id, mission_id)` transitions to `FAILED` with `mission_approval_not_granted`.

## 4. Startup Reconciliation
If the JARVIS process is killed, crashes, or restarts during mission execution:
- `RuntimeRepository.reconcile_missions()` identifies any mission in `RUNNING` or `WAITING` status.
- The status is transitioned to `FAILED` with `error_code="process_restarted"`.
- Interrupted runs are recorded in audit logs and emitted over the event bus.
