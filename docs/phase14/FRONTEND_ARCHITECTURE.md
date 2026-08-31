# Phase 14 frontend architecture

The Command Center is a product-owned dependency-free static frontend:

```text
ui/src/{index.html,styles.css,app.js}
        -> python ui/build_frontend.py
src/jarvis/ui_static/{index.html,styles.css,app.js}
        -> CoreHttpServer /v1/app/*
```

`ui/frontend.lock.json` records the deliberate zero-dependency runtime. No
Node/npm process is needed at product startup, and the build is deterministic
because it copies a fixed entrypoint set and rejects remote URL references.
Python package data includes the compiled static assets.

The browser shell is a projection/control surface. It fetches fresh state on
load and at a bounded two-second cadence, uses canonical conversation and
memory APIs, and never invents missions, devices, progress percentages, or
health. Text chat uses the existing `AgentRuntime` through
`CoreApplication.send_message`; it is not a second brain.

The central core visualization maps CSS state classes to the state returned by
the experience projection. Reduced motion is respected. Dynamic values are
escaped before insertion, and the application does not render arbitrary model
HTML.

Daily desktop launch opens `/app` through the existing loopback HTTP server.
The known Tk window remains available for first-run setup, audio/device
configuration, repair, and diagnostics, but is hidden during normal browser
launch so the Command Center is the primary product surface.
