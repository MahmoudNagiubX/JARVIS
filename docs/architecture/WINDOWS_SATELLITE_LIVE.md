# Live Windows satellite

The runnable client is `python -m jarvis.satellite_agent`. It uses the
product-owned `WindowsNativeComputerController` and accepts only the typed
operations listed below:

`list_processes`, `inspect_file`, `search_files`, `open_file`, `open_folder`,
`open_application`, and `stop_safe_process`.

The client must receive an owner-bound credential through an environment
secret or an external secret manager. It keeps that value in memory and sends
it only as an Authorization header. It does not place credentials in URLs,
JSON bodies, logs, or source control.

Example environment (loopback core only):

```powershell
$env:JARVIS_CORE_URL = "http://127.0.0.1:8787"
$env:JARVIS_OWNER_ID = "owner-id"
$env:JARVIS_IDENTITY_ID = "identity-id"
$env:JARVIS_NODE_ID = "windows-primary"
$env:JARVIS_SATELLITE_CREDENTIAL = "<external-secret>"
$env:PYTHONPATH = "src"
python -m jarvis.satellite_agent
```

Use `scripts/phase09/run_windows_satellite.ps1` for the same bounded launch
contract. Host-level restart policy belongs to Task Scheduler or an existing
service wrapper and must restart this exact command with the same working
directory and environment. The repository does not silently install a task,
elevate privileges, or claim physical acceptance from a mock.

Acceptance requires a real Windows process, a real owner-bound enrollment,
heartbeat freshness, a harmless observation, an allowlisted action, rejection
of an unsupported typed operation, reconnect, revocation, and evidence of
offline recovery. If the core is unavailable, the client reports transport
failure and never reports command success.
