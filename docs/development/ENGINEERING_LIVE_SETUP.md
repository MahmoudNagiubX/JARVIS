# Engineering live setup

Jupyter and KiCad are specialist adapters. A deployment injects a provider and
creates an `EngineeringWorkspace` with explicit read/write roots, allowed
tools, timeout, and approval policy. Inspect is read-only; edit/execute/restart
remain approval-aware and auditable.

The Phase 06 default providers are unconfigured. Live Jupyter/KiCad acceptance
requires an existing installation and a disposable scoped workspace. No live
installation was verified on the workstation; adapter-level acceptance is the
only result recorded.
