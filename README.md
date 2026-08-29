# JARVIS Core Runtime

This repository is the Phase 02 core runtime for the JARVIS Personal AI OS.
The selected architectural spine is the local BMO/JARVIS platform: its
product boundaries, identity/device authority, model gateway, tool approval
workflow, audit records, and application lifecycle are the closest match for
an authority-first core.

Phase 02 keeps those boundaries and adds a dependency-free, durable local
runtime: owner/device authority, SQLite persistence, model routing, a bounded
agent loop, approval-controlled tools, typed Windows satellite commands,
voice orchestration with barge-in cancellation, and loopback HTTP/CLI entry
points. No model is loaded and no hardware or server is opened at import or
composition time.

## Run the local runtime

```powershell
$env:PYTHONPATH = "src"
python -m jarvis
python -m jarvis --text "hello JARVIS"
python -m jarvis --serve --port 8787
```

## Run tests without installing dependencies

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

See [docs/RUNNING_JARVIS.md](docs/RUNNING_JARVIS.md),
[docs/TESTING.md](docs/TESTING.md), and the architecture documents for
operational boundaries and known Phase 03+ work.
