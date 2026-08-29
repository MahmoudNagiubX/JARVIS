# Performance and retention

The standard-library `PerformanceProfiler` records wall-clock and process CPU
time for bounded acceptance operations. `ObservabilityService` keeps
low-cardinality event/failure/latency totals and does not retain secrets.

Use:

```powershell
$env:PYTHONPATH = "src"
python -m unittest tests.test_phase_six_integration -v
```

The SQLite event log has an explicit dry-run retention API:
`RuntimeRepository.prune_events(before, dry_run=True)`. Only the operational
event table is eligible; memory, conversations, goals, identities, research
ledgers, and `audit_records` are not removed. Set `dry_run=False` only after a
backup, a reviewed cutoff, and an operator-approved maintenance window.

Production hosts should rotate stdout/stderr at the host boundary, retain
audit records longer than operational events, monitor startup time, event
failure totals, model latency, database health, and queue/backpressure
signals, and alert on repeated `process_restarted` recovery.
