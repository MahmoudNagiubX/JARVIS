# JARVIS Foundation

This repository is the Phase 01 foundation for the JARVIS Personal AI OS.
The selected architectural spine is the local BMO/JARVIS platform: its
product boundaries, identity/device authority, model gateway, tool approval
workflow, audit records, and application lifecycle are the closest match for
an authority-first core.

Phase 01 intentionally contains no downloaded models, network clients, audio
drivers, or provider SDKs. It provides typed contracts, a normalized event
envelope, an in-process event bus, safe in-memory implementations, and a
minimal start/ready/shutdown lifecycle. All real integrations are deferred to
the migration backlog and must enter through these boundaries.

## Run the foundation smoke check

```powershell
$env:PYTHONPATH = "src"
python -m jarvis
```

## Run tests without installing dependencies

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

The repository is local-only at this phase. No remote is configured and work
stops before Mega Phase 02.
