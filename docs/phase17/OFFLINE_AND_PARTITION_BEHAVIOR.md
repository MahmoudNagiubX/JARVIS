# Offline & Partition Behavior

## Partition Behavior & Fail-Safe Modes
1. **Venom Node Partition / Disconnection**:
   - If Venom becomes unreachable, NIGHTFURY marks Venom health status as `OFFLINE`.
   - Local core reasoning, voice interactions, and Command Center UI remain 100% operational on NIGHTFURY.
   - Database backups are buffered locally until Venom connectivity is restored.
2. **Satellite Node Partition**:
   - Satellites failing to heartbeat within 3 heartbeat intervals are transitioned to `DEGRADED` and then `OFFLINE`.
   - Voice routing automatically excludes offline satellites and falls back to primary desktop audio.
   - If user explicitly targets an offline device (`@device`), the system fails closed with `target_device_offline` rather than making silent unauthorized assumptions.
3. **Internet Outage / Full LAN Isolation**:
   - `OfflineModeService` detects offline state.
   - All reasoning runs locally via Qwen-2.5-Coder-7B-Instruct on RTX 4080 GPU.
   - No external cloud dependencies or telemetry leaks occur.
