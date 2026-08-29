# Testing

Run the dependency-free suite with:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

The suite covers contracts/lifecycle, identity and device enrollment,
permission allow/deny, durable approvals and resume,
audit/event persistence, model mock routing, text flow and replay,
cancellation boundaries, worker handling, typed satellite execution, and
voice TTS cancellation/barge-in. The runtime includes memory extraction/search/edit,
World State fusion/expiry/conflict handling, bounded goals, proactive cooldown
and safe action routing, personalization/offline/context behavior, and the
loopback resource APIs, typed computer approval, bounded browser
reads, device fabric heartbeats/revocation, home safety boundaries, restricted
MQTT, communications approval, notification deduplication, room voice
handoff, capability registration, and the new loopback endpoints.

The suite also covers durable research restart reconciliation, backup/restore,
injected PostgreSQL reconnect health, local model probing, lifecycle,
redaction, retention, and WebSocket framing tests. Tests use deterministic
providers and adapters. They do not prove a real
PostgreSQL/pgvector deployment, GPU inference, physical voice acceptance,
external Windows satellite transport, Playwright browser control, Home
Assistant/MQTT hardware, OS notification delivery, or external communication
accounts.
