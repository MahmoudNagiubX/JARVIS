# Home Routines

The current safe routine IDs are `focus_lighting`, `study_lighting`,
`work_start_scene`, `sleep_scene`, `leave_safe_scene`, and `return_scene`.
They select only entities returned by the configured Home transport and call
the existing `HomeActionService` for every action.

Configure Home Assistant or an in-memory transport for local tests. Entity
IDs are never invented. Locks, alarms, security overrides, and life-safety
actions remain blocked regardless of mode or voice request.
