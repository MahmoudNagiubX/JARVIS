# Deployment

JARVIS is a local-first Python package with no runtime dependencies. From the
canonical repository:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
python -m jarvis --status
python -m jarvis --serve --port 8787
```

The default service is loopback-only. Keep the process under a dedicated least
privilege Windows account, use an explicit working directory, and provide
`JARVIS_DATABASE_PATH` as a writable application-data path. Do not expose port
8787 publicly or place credentials in source control, command history, URLs,
or logs.

The process can be hosted by Windows Task Scheduler, a user Startup shortcut,
or an existing service wrapper. The repository does not silently create a
scheduled task or elevate privileges. Configure restart-on-failure in the
chosen host and verify it with the startup/recovery checklist.

Optional local model deployment points only at an already-running Ollama
endpoint. PostgreSQL, pgvector, Playwright, audio, satellite, engineering,
Venom, Home Assistant/MQTT, and communications are deployment-owned adapters;
install/configure them separately and record their acceptance evidence.

For the Phase 09 distributed profile, keep the core and model endpoints on
loopback and launch an authorized Windows satellite with
`scripts/phase09/run_windows_satellite.ps1`. Configure host-level restart in
the existing service/Task Scheduler layer; do not install a new supervisor
implicitly. See `docs/architecture/NODE_TRANSPORT.md` and
`docs/architecture/WINDOWS_SATELLITE_LIVE.md`.
