# JARVIS Core Runtime

This repository is the Phase 04 core runtime for the JARVIS Personal AI OS.
The selected architectural spine is the local BMO/JARVIS platform: its
product boundaries, identity/device authority, model gateway, tool approval
workflow, audit records, and application lifecycle are the closest match for
an authority-first core.

Phase 03 keeps those boundaries and adds a dependency-free, durable local
runtime: owner/device authority, SQLite persistence, model routing, a bounded
agent loop, approval-controlled tools, typed Windows satellite commands,
voice orchestration with barge-in cancellation, product-owned memory, separate
World State, bounded goals, deterministic proactive findings, personalization,
offline state, and loopback HTTP/CLI entry points. Phase 04 adds bounded
computer/browser actions, a unified device fabric, Home Assistant/MQTT seams,
room voice routing, communications drafts/sends, capability inventory, and
local notifications. No model is loaded and no hardware or server is opened
at import or composition time.

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
operational boundaries and current Phase 04 limits.
