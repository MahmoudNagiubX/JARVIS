# Mission runtime

Missions are bounded executable plans above the durable `GoalEngine`. A goal
captures an enduring objective; a mission captures one inspectable attempt to
make progress toward that objective or toward an explicit user request.

`MissionService` owns lifecycle state, budgets, checkpoints, evidence, and
restart reconciliation. It does not own tools, workers, permissions, or
approvals. Planned consequential steps enter `waiting_approval`; replanning
preserves completed steps, records a reason, and consumes `max_replans`.

Every mission has limits for steps, elapsed time, tool calls, worker runs,
replans, and external actions. External actions default to zero. A restart
fails transient `running`, `waiting`, and `waiting_approval` missions with
`process_restarted` evidence rather than pretending they resumed.
