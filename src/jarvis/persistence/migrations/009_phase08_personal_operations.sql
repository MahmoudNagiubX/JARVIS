-- Phase 08 bounded personal-operations persistence.
-- SQLiteDatabase applies the equivalent idempotent schema at bootstrap; this
-- file keeps the PostgreSQL migration sequence explicit for future adapters.
CREATE TABLE IF NOT EXISTS personal_modes (
    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, mode TEXT NOT NULL,
    source TEXT NOT NULL, started_at TEXT NOT NULL, expires_at TEXT,
    metadata_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS focus_sessions (
    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, status TEXT NOT NULL,
    goal_id TEXT, mission_id TEXT, started_at TEXT NOT NULL, ends_at TEXT,
    ended_at TEXT, interruption_reason TEXT, metadata_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS communication_followups (
    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, thread_id TEXT NOT NULL,
    message_id TEXT, direction TEXT NOT NULL, status TEXT NOT NULL,
    summary TEXT NOT NULL, due_at TEXT NOT NULL, created_at TEXT NOT NULL,
    resolved_at TEXT, related_goal_id TEXT, related_mission_id TEXT,
    metadata_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS auto_send_rules (
    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, channel TEXT NOT NULL,
    recipient_allowlist_json TEXT NOT NULL, message_class TEXT NOT NULL,
    allowed_context_json TEXT NOT NULL, max_frequency INTEGER NOT NULL,
    window_seconds REAL NOT NULL, allowed_time_start TEXT,
    allowed_time_end TEXT, sensitivity TEXT NOT NULL,
    approval_requirement TEXT NOT NULL, enabled INTEGER NOT NULL,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notification_delivery_attempts (
    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, notification_id TEXT NOT NULL,
    channel TEXT NOT NULL, target TEXT, status TEXT NOT NULL, reason TEXT,
    fingerprint TEXT, attempted_at TEXT NOT NULL, metadata_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS routine_runs (
    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, routine_id TEXT NOT NULL,
    status TEXT NOT NULL, result_json TEXT NOT NULL, started_at TEXT NOT NULL,
    completed_at TEXT
);
