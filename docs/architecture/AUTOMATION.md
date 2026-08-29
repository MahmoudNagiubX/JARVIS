# Safe workflow automation

Automation is a declarative rule layer, not a second scheduler. Schedule
ticks are registered with the existing `BackgroundScheduler`; event rules use
the existing EventBus. A rule contains a trigger, structured conditions,
cooldown, risk, and actions targeting only skills, missions, notifications, or
briefings. Raw shell, Python, and command targets are rejected.

Skill/tool execution still passes through the normal permission and approval
pipeline. Disabled rules, false conditions, cooldowns, unavailable context,
and approval-required actions are recorded as suppressed or pending outcomes.
