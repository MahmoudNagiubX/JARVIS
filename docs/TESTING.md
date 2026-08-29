# Testing

Run the dependency-free suite with:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

The suite covers the Phase 01 contracts/lifecycle and Phase 02 identity and
device enrollment, permission allow/deny, durable approvals and resume,
audit/event persistence, model mock routing, text flow and replay,
cancellation boundaries, worker handling, typed satellite execution, and
voice TTS cancellation/barge-in.

Tests use deterministic providers and adapters. They do not prove a real
PostgreSQL/pgvector deployment, GPU inference, physical voice acceptance, or
an external Windows satellite transport.
