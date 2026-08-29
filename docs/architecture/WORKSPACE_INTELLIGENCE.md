# Workspace intelligence

`WorkspaceIntelligenceService` works only on a project root explicitly
provided and registered by the owner. Discovery is deterministic and bounded:
it checks top-level project markers, a small changed-file list, and a compact
repo map of important files, modules, tests, entry points, and configuration.
It does not recursively index the disk or place complete repositories in model
context.

Project metadata is durable and includes branch/status, inferred commands,
recent failures/successes, related work, and known services. Existing
read-only world-state workspace observation remains the observation authority.
