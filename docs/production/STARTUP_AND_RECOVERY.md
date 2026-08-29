# Startup and recovery

Startup is explicit: compose, reconcile stale `queued`/`running` work, start
the scheduler, emit `system.bootstrap.started`, then
`system.bootstrap.ready`. Shutdown stops scheduled work, stops voice if active,
emits shutdown events, closes projections/observability, closes SQLite, and
closes the event bus.

```powershell
$env:PYTHONPATH = "src"
python -m jarvis --status
python -m jarvis --serve
```

If a process dies, the next process marks process-owned core and research
transient runs failed with `process_restarted`. This is conservative recovery:
it does not pretend to resume an unsafe in-flight tool action. Completed
research sources/evidence/reports remain queryable from the durable ledger.

For a host-level restart, configure the Windows host to restart the same
command with the same working directory and environment. Confirm loopback
`/v1/health`, then inspect the event and research ledgers. Never use a blind
redeploy, public bind, or data reset as a recovery step.
