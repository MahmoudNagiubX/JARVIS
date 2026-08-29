# Engineering copilot

Engineering sessions live under `jarvis.engineering` and use product-owned
contracts for workspace, session, action, artifact, and result. A workspace
has explicit read and write scopes, an allowlist of tools, a timeout, risk
level, and approval policy. Targets outside scope are rejected. There is no
generic shell action.

`JupyterEngineeringProvider` and `KiCadEngineeringProvider` are injected
provider boundaries. The Jupyter donor at
`C:\Jarivs\08_engineering\jupyter-mcp` was inspected read-only for capability
and scope concepts; no donor code was imported or copied. KiCad has no local
donor in the discovered workspace, so its provider remains a declared IPC
boundary.

Engineering write/execute/restart actions pass the normal identity, device,
permission, approval, audit, event, and result path. `EngineeringWorker`
wraps the existing `LocalWorkerRuntime` with `WorkerCategory.ENGINEERING`; it
does not introduce another agent runtime.
