# JARVIS goal engine

Goals are persisted state machines, not an unrestricted recursive LLM loop.
Each goal has an owner, title/description, status, priority, target date,
constraints, budgets, plan/steps, dependencies, checkpoints, next action,
review timestamp, and completion criteria.

The engine supports create, plan, activate, pause, resume, cancel, complete,
checkpoint, and bounded replan. Step and replan budgets are validated before
mutation; the default maximum is finite and the hard step ceiling is 100.
Invalid transitions fail closed. Goal events and audit records make lifecycle
changes inspectable.

The domain model is product-owned. LangGraph was not added as a runtime
dependency or authority. The loopback API exposes goal listing, creation,
patching, and pause/resume/cancel control under `/v1/goals`.

