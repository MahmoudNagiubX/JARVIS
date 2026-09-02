# Phase 17 Acceptance Report

## Final acceptance summary

- **Mega Phase**: Phase 17 - Venom, Home, Multi-Device & Room Fabric.
- **Base commit**: `c3dc5abe20adc3d23605326ff35c9e2843477cde`.
- **Architecture**: Option A - NIGHTFURY authoritative Core/SQLite/VoiceCore/AgentRuntime; Venom is a lightweight infrastructure node.
- **Phase 17 focused tests**: 66 passed, 0 failed.
- **Phases 13-16 regression**: 218 passed, 11 subtests passed, 0 failed.
- **Full repository Python suite**: 502 passed, 36 subtests passed, 0 failed.
- **Frontend Vitest**: 75 passed in 14 files, 0 failed.
- **Frontend build**: TypeScript and Vite build clean; 68 modules transformed.
- **Security**: `npm audit --audit-level=high` found 0 vulnerabilities; compileall and diff checks passed.

## Closure gates

- Authenticated LAN node transport, private Core URL policy, device revocation idempotency, canonical Home approvals, truthful MQTT delivery, Venom heartbeat/backoff, room owner/device binding, and remote execution deadlines pass in deterministic local tests.
- The UI/Core HTTP server remains loopback-only. The node adapter is separate, authenticated, private-client restricted, and node-route-only.
- Venom `backup_receiver`, `event_relay`, and `ha_bridge` remain `NOT_CONFIGURED`; MQTT reports actual broker health and is not advertised as successful without a publisher.
- Enrollment remains `REGISTERED` until authenticated connect/heartbeat evidence.

## Physical boundary

Physical Venom deployment is **BLOCKED_AUTH / BLOCKED_WAITING_FOR_CREDENTIALS**. Owner evidence identifies `venom-server` at `192.162.1.33` with SSH fingerprint `SHA256:bhEw1uFGz6QnUeNfoA58u5T/xTzw0Le0KTZc26mTpPc`; non-interactive SSH authentication was unavailable. No remote mutation, credential storage, Home Assistant install, ESP32 acceptance, or room-acoustic acceptance is claimed.

Phase 18 and Phase 19 physical work were not started.
