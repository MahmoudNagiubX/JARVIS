# Satellite LAN Transport & Long-Polling Protocol

## Authenticated Local Transport
Satellite devices communicate with the authoritative Core over authenticated local LAN transport:
- **Long-Poll Endpoint**: `GET /satellites/commands?session_id={id}&wait_seconds=20`
- **Authentication**: `Authorization: Bearer <device_credential>` header or HTTP POST session credential. Query parameter credentials are strictly prohibited (`PermissionError("query_credentials_not_allowed")`).
- **Heartbeat & Liveness**: Satellites transmit `POST /satellites/heartbeat` with sequence number and telemetry. Devices failing to heartbeat within `heartbeat_interval_seconds * 3` are automatically marked `DEGRADED` and then `OFFLINE`.

## Network Origin Policy

- `live-distributed` uses the shared `DEFAULT_PRIVATE_LAN` policy for RFC1918/link-local/private IPv6 origins, plus only explicitly configured bounded `trusted_lan_cidrs`.
- `local` and `test` may use loopback only when the caller explicitly selects that mode; the satellite client defaults to `live-distributed`.
- A non-RFC1918 configured owner subnet is labeled `EXPLICIT_LOCAL_TRUST_OVERRIDE`, never `PRIVATE`. Public IPs, wildcard trust, multicast, unspecified, malformed CIDRs, URL userinfo, paths, queries, and fragments remain blocked.

## Payload Bounds & Quarantine
- **Command Payloads**: Bounded to a maximum size of 64 KB.
- **Command Observations**: Results returned from satellites are capped at 256 KB.
- **Untrusted Metadata Defense**: All telemetry strings from satellite devices undergo character escaping and control-character filtering (`sanitize_untrusted_text`, `sanitize_untrusted_metadata`) before being injected into World State or LLM prompt contexts.
