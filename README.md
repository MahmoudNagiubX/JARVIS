# JARVIS Core Runtime

This repository is the product-owned core runtime for the JARVIS Personal AI OS.
The selected architectural spine is the local BMO/JARVIS platform: its
product boundaries, identity/device authority, model gateway, tool approval
workflow, audit records, and application lifecycle are the closest match for
an authority-first core.

The runtime provides dependency-free local durability, owner/device authority,
model routing, a bounded agent loop, approval-controlled tools, typed Windows
satellite commands, voice orchestration, product-owned memory and World State,
bounded goals and proactive findings, personalization, offline state,
computer/browser/device/home/communications/notification seams, event-derived
experience projections, a HUD, evidence-led research, bounded engineering
workers, on-demand perception, observability, and declarative intelligence.
No model is loaded and no hardware, capture loop, or server is opened at import
or composition time.

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
operational boundaries and current runtime limits.
