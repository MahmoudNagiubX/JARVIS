# HUD

The runtime provides a dependency-free static HUD at `GET /v1/hud`. It is an
original dark technical console built from local HTML, CSS, and JavaScript;
there are no Marvel assets, copied donor UI assets, CDN dependencies, or
browser-side business rules.

The console displays system state, model/offline health, event counts, runs,
workers, devices, goals, approvals, research, engineering, voice, and the
bounded event timeline. State data is fetched through the authenticated
experience API. The shell itself contains no credentials or secrets.

The current stdlib adapter uses SSE snapshots for broad client compatibility.
Replacing it with authenticated WebSocket transport is an edge-adapter change,
not a change to the projection or authority model.
