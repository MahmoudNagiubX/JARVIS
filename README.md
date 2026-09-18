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

## Desktop product quick start

1. Launch JARVIS from the current-user Start Menu shortcut (`JARVIS.lnk`),
   or run `pythonw.exe -m jarvis.desktop` from the checkout.
2. Finish the Setup items shown by the app.
3. Log into selected services only in the dedicated JARVIS browser profile;
   never attach the normal Brave profile.
4. Talk or type, and treat every consequential result as complete only after
   JARVIS reports independent verification.

The desktop release remains a truthful partial candidate until owner-authenticated
service workflows and physical voice/lifecycle acceptance are completed. See
[`docs/audits/JARVIS_FINAL_COMPLETION_AUDIT.md`](docs/audits/JARVIS_FINAL_COMPLETION_AUDIT.md)
for the current gate matrix.
