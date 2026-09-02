# Venom Node Operations, Health & Backup Verification

## Operations & Service Monitoring
- **Service Watchdog**: `VenomNode` probes systemd service health for `mosquitto` and `backup_receiver`. Health states (`active`, `inactive`, `failed`) are published in experience state projections.
- **Storage Utilization**: Tracks total, free, and used disk space. Categorizes storage as `healthy` (< 80% usage), `warning` (80–95% usage), or `critical` (> 95% usage).
- **Health Check Probe (`scripts/venom/health_check.py`)**: Runs periodic local checks and returns structured JSON health reports.

## Backup Ingestion & Verification
Venom verifies received SQLite backups via `verify_backup()`:
1. **Magic Header Check**: Verifies the first 16 bytes match the SQLite format: `SQLite format 3\000`. Rejects corrupt or invalid file types.
2. **SHA-256 Checksum Validation**: Computes hash of received archive and matches against core manifest.
3. **Atomic Retention**: Backups are written to `/opt/jarvis-venom/backups/sqlite/` with timestamped filenames and preserved across rollbacks.
