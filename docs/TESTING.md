# Testing

Run the dependency-free suite with:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

The suite covers the Phase 01 contracts/lifecycle, Phase 02 identity and
device enrollment, permission allow/deny, durable approvals and resume,
audit/event persistence, model mock routing, text flow and replay,
cancellation boundaries, worker handling, typed satellite execution, and
voice TTS cancellation/barge-in. Phase 03 adds memory extraction/search/edit,
World State fusion/expiry/conflict handling, bounded goals, proactive cooldown
and safe action routing, personalization/offline/context behavior, and the
loopback resource APIs. Phase 04 adds typed computer approval, bounded browser
reads, device fabric heartbeats/revocation, home safety boundaries, restricted
MQTT, communications approval, notification deduplication, room voice
handoff, capability registration, and the new loopback endpoints.

Tests use deterministic providers and adapters. They do not prove a real
PostgreSQL/pgvector deployment, GPU inference, physical voice acceptance,
external Windows satellite transport, Playwright browser control, Home
Assistant/MQTT hardware, OS notification delivery, or external communication
accounts.
