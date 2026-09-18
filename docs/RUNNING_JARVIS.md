# Running JARVIS

From the repository root:

```powershell
$env:PYTHONPATH = "src"
python -m jarvis
python -m jarvis --text "hello JARVIS"
python -m jarvis --serve --port 8787
```

The default database is `data/jarvis.sqlite3` and is ignored by Git. Tests
use an in-memory database. The HTTP adapter is loopback-only and exposes
`GET /health`, `GET /v1/events`, `GET /v1/events/stream`, `GET /v1/approvals/{id}`,
`POST /v1/messages`, `POST /v1/approvals/{id}`, and
`POST /v1/runs/{id}/cancel`.

Mutation endpoints require `identity_id`, `device_id`, and the issued device
`credential` in the JSON body. The CLI's demo principal is a local convenience
for the direct application service and does not expose its credential.

Use `JARVIS_DATABASE_PATH` to select another local database path. Secrets are
not placed in configuration files; issued credentials are returned only to
the enrollment caller.

## Desktop product quick start

1. Launch JARVIS from the current-user Start Menu shortcut (`JARVIS.lnk`),
   or use `pythonw.exe -m jarvis.desktop` from the checkout.
2. Finish the Setup items shown by the app.
3. Log into selected services only in the dedicated JARVIS browser profile.
4. Talk or type; JARVIS must independently verify consequential actions.

Setup keeps owner-specific identity and credentials in the local product
stores. Do not copy them into settings, prompts, logs, or this document.
