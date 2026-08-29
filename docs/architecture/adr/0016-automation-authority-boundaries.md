# ADR 0016: automation preserves authority boundaries

Automation reuses the existing scheduler and EventBus. Its actions can target
only product services; it cannot execute raw commands, bypass approvals, or
create a second scheduler or tool registry.
