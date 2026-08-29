# Home Orchestration

`HomeContextService` projects only configured Home Assistant entities into
transient World State, filtering attributes to a safe normalized view.
`HomeRoutineService` provides small templates for lighting and safe scenes;
execution delegates to the existing `HomeActionService` and its permission,
audit, transport, and blocked-action boundaries.

Locks, alarms, security overrides, and life-safety controls remain blocked.
If Home Assistant is unavailable, local personal operations continue and the
context or routine reports `unavailable`/`partial`; no fake entity or success
is fabricated.
