# Device Enrollment Security — Cryptographic Tokens & Revocation

## Enrollment Lifecycle & Flow

```
+---------------+              +-------------------------------------+              +--------------------+
| Unenrolled    |              | Authoritative Core (NIGHTFURY)      |              | Command Center UI  |
| Satellite     |              | DeviceFabricService                 |              | / Admin API        |
+-------+-------+              +------------------+------------------+              +---------+----------+
        |                                         |                                           |
        |                                         |<--- Issue Enrollment Ticket --------------+
        |                                         |     (Name, Role, Scopes, Caps, TTL)       |
        |                                         |                                           |
        |                                         |---> Return One-Time Code & Ticket ID ---->|
        |                                         |                                           |
        |<--- Operator enters One-Time Code ------|                                           |
        |                                         |                                           |
        |--- POST /devices/enroll --------------->|                                           |
        |    (Code, DeviceId, Platform, Caps)     |                                           |
        |                                         |-- Validate Hash & Expiry                  |
        |                                         |-- Generate Cryptographic Credential       |
        |                                         |-- Store Hashed Secret in DB               |
        |                                         |-- Emit "device.enrolled" Event            |
        |                                         |                                           |
        |<-- Return Accepted + Bearer Token ------|                                           |
        |                                         |                                           |
        |--- Authenticated Long-Poll / HB ------->|                                           |
```

## Security Guarantees
1. **Cryptographic Secret Hashing**: Generated device credentials and secrets are hashed using salted PBKDF2-HMAC-SHA256 (`_hash_secret`) before storage; raw secrets and bearer credentials are never persisted in plaintext in the database.
2. **Short-Lived Tickets**: Default TTL is 10 minutes. Expired or already consumed tickets are rejected immediately (`invalid_or_expired_enrollment_code`).
3. **Audit Safety**: Credential issuance and revocation events omit raw tokens and secret keys from event payloads and durable audit records.
4. **Immediate Revocation Cascade**:
   - Calling `revoke(owner_id, device_id)` marks device status as `REVOKED`.
   - Cleans all active sessions in the database.
   - Cleans device presence from `PresenceService` (`clear_device`).
   - Revokes all associated voice endpoints in `VoiceRoutingService` (`revoke_device_endpoints`).
   - Any subsequent heartbeat or tool call from the revoked device fails closed with `PermissionError("device_revoked")`.
