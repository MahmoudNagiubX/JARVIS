# HUD

The runtime provides a dependency-free static HUD at `GET /v1/hud`. It is an
original dark technical console built from local HTML, CSS, and JavaScript;
there are no Marvel assets, copied donor UI assets, CDN dependencies, or
browser-side business rules.

The console displays system state, model/offline health, event counts, runs,
workers, devices, goals, approvals, research, engineering, voice, presence,
attention, current mode/focus, communication follow-ups, home context, and
the bounded event timeline. State data is fetched through the authenticated
experience API. The shell itself contains no credentials or secrets.

The current stdlib adapter uses SSE snapshots for broad client compatibility.
Replacing it with authenticated WebSocket transport is an edge-adapter change,
not a change to the projection or authority model.

Phase 14 adds the primary local Command Center at `/v1/app`. The legacy HUD
remains available as a compatibility and diagnostic fallback; normal desktop
launch opens the Command Center through the same loopback server.
