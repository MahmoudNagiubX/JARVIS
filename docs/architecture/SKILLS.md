# Product-owned skills

Skills are declarative, inspectable procedures. The registry stores a small
manifest index; `SkillLoader` reads bounded Markdown instructions only after a
skill is selected. `SkillExecutor` routes tool steps through the existing
ToolRegistry, PermissionEngine, ApprovalEngine, Audit, and EventBus.

The initial catalog is `project_status`, `run_tests`, `debug_failed_build`,
`start_dev_environment`, `research_and_report`, `daily_brief`,
`system_health_check`, and `backup_jarvis`. Unavailable adapters remain
unavailable; no fake integration is registered. Learned procedures begin as
drafts, require review, use known actions, and cannot raise their autonomy or
authority. Manifests and versions are durable and disableable.
