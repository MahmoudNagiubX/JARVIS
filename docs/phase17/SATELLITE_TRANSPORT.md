# Satellite LAN Transport & Long-Polling Protocol

## Authenticated Local Transport
Satellite devices communicate with the authoritative Core over loopback/local LAN transport:
- **Long-Poll Endpoint**: `GET /satellites/commands?session_id={id}&wait_seconds=20`
- **Authentication**: `Authorization: Bearer <device_credential>` header or HTTP POST session credential. Query parameter credentials are strictly prohibited (`PermissionError("query_credentials_not_allowed")`).
- **Heartbeat & Liveness**: Satellites transmit `POST /satellites/heartbeat` with sequence number and telemetry. Devices failing to heartbeat within `heartbeat_interval_seconds * 3` are automatically marked `DEGRADED` and then `OFFLINE`.

## Payload Bounds & Quarantine
- **Command Payloads**: Bounded to a maximum size of 64 KB.
- **Command Observations**: Results returned from satellites are capped at 256 KB.
- **Untrusted Metadata Defense**: All telemetry strings from satellite devices undergo character escaping and control-character filtering (`sanitize_untrusted_text`, `sanitize_untrusted_metadata`) before being injected into World State or LLM prompt contexts.
