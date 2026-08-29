"""SQLite persistence adapter used for local durability and offline tests.

The domain only depends on repositories. SQLite is the Phase 03 zero-install
adapter; the schema is deliberately close to the BMO relational model so a
future PostgreSQL adapter does not change the product contracts.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import Iterator


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS owners (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS identities (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL REFERENCES owners(id),
    display_name TEXT NOT NULL,
    kind TEXT NOT NULL,
    roles_json TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS devices (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL REFERENCES owners(id),
    display_name TEXT NOT NULL,
    device_kind TEXT NOT NULL,
    platform TEXT NOT NULL,
    capabilities_json TEXT NOT NULL,
    scopes_json TEXT NOT NULL,
    status TEXT NOT NULL,
    trust_state TEXT NOT NULL,
    last_seen_at TEXT,
    revoked_at TEXT
);
CREATE TABLE IF NOT EXISTS credentials (
    id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL REFERENCES devices(id),
    public_id TEXT NOT NULL UNIQUE,
    secret_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_used_at TEXT,
    revoked_at TEXT
);
CREATE TABLE IF NOT EXISTS enrollments (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL REFERENCES owners(id),
    code_hash TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    device_kind TEXT NOT NULL,
    platform TEXT NOT NULL,
    software_version TEXT,
    scopes_json TEXT NOT NULL,
    capabilities_json TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    consumed_at TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL REFERENCES owners(id),
    device_id TEXT NOT NULL REFERENCES devices(id),
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    closed_at TEXT
);
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL REFERENCES owners(id),
    created_by_device_id TEXT NOT NULL REFERENCES devices(id),
    title TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_message_at TEXT
);
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    session_id TEXT REFERENCES sessions(id),
    run_id TEXT,
    author_device_id TEXT REFERENCES devices(id),
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    client_message_id TEXT UNIQUE,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    session_id TEXT NOT NULL REFERENCES sessions(id),
    request_device_id TEXT NOT NULL REFERENCES devices(id),
    trigger_message_id TEXT NOT NULL REFERENCES messages(id),
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    cancel_requested_at TEXT,
    completed_at TEXT,
    model_request_id TEXT,
    model_id TEXT,
    model_digest TEXT,
    finish_reason TEXT,
    prompt_usage INTEGER,
    output_usage INTEGER,
    latency_ms REAL,
    failure_category TEXT,
    failure_code TEXT,
    correlation_id TEXT NOT NULL,
    context_json TEXT NOT NULL DEFAULT '{}',
    context_truncated INTEGER NOT NULL DEFAULT 0,
    pending_approval_id TEXT
);
CREATE TABLE IF NOT EXISTS events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    category TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    causation_id TEXT,
    session_id TEXT,
    actor_id TEXT,
    payload_json TEXT NOT NULL,
    severity TEXT NOT NULL,
    state TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    requester_id TEXT NOT NULL,
    device_id TEXT,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    preview_json TEXT NOT NULL,
    status TEXT NOT NULL,
    decided_by TEXT,
    decided_at TEXT,
    decision_reason TEXT
);
CREATE TABLE IF NOT EXISTS audit_records (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    actor_id TEXT,
    device_id TEXT,
    correlation_id TEXT NOT NULL,
    outcome TEXT NOT NULL,
    reason_code TEXT,
    metadata_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tool_calls (
    id TEXT PRIMARY KEY,
    run_id TEXT,
    name TEXT NOT NULL,
    arguments_json TEXT NOT NULL,
    argument_digest TEXT NOT NULL,
    status TEXT NOT NULL,
    approval_id TEXT,
    output_json TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, ordinal);
CREATE INDEX IF NOT EXISTS idx_events_correlation ON events(correlation_id, sequence);
CREATE INDEX IF NOT EXISTS idx_audit_correlation ON audit_records(correlation_id, occurred_at);

CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL REFERENCES owners(id),
    category TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    structured_data_json TEXT NOT NULL,
    source TEXT NOT NULL,
    source_reference TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_accessed_at TEXT,
    confidence REAL NOT NULL,
    sensitivity TEXT NOT NULL,
    scope TEXT NOT NULL,
    valid_from TEXT,
    valid_until TEXT,
    retention_policy TEXT NOT NULL,
    status TEXT NOT NULL,
    supersedes TEXT,
    tags_json TEXT NOT NULL,
    pinned INTEGER NOT NULL DEFAULT 0,
    archived INTEGER NOT NULL DEFAULT 0,
    embedding_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_memories_owner_category ON memories(owner_id, category, status);
CREATE INDEX IF NOT EXISTS idx_memories_owner_updated ON memories(owner_id, updated_at);

CREATE TABLE IF NOT EXISTS world_observations (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL REFERENCES owners(id),
    source TEXT NOT NULL,
    source_reference TEXT,
    observed_at TEXT NOT NULL,
    subject TEXT NOT NULL,
    value_json TEXT NOT NULL,
    confidence REAL NOT NULL,
    freshness_seconds REAL,
    expires_at TEXT,
    authority_level INTEGER NOT NULL,
    conflict_state TEXT NOT NULL,
    device_id TEXT,
    scope TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_world_observations_owner_subject ON world_observations(owner_id, subject, observed_at);

CREATE TABLE IF NOT EXISTS world_facts (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL REFERENCES owners(id),
    key TEXT NOT NULL,
    value_json TEXT NOT NULL,
    source TEXT NOT NULL,
    source_reference TEXT,
    observed_at TEXT NOT NULL,
    freshness REAL,
    expires_at TEXT,
    confidence REAL NOT NULL,
    authority_level INTEGER NOT NULL,
    conflict_state TEXT NOT NULL,
    device_id TEXT,
    scope TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_world_facts_owner_key ON world_facts(owner_id, key);

CREATE TABLE IF NOT EXISTS world_conflicts (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL REFERENCES owners(id),
    key TEXT NOT NULL,
    fact_ids_json TEXT NOT NULL,
    reason TEXT NOT NULL,
    detected_at TEXT NOT NULL,
    resolved INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_world_conflicts_owner ON world_conflicts(owner_id, resolved, detected_at);

CREATE TABLE IF NOT EXISTS goals (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL REFERENCES owners(id),
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL,
    priority INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    target_date TEXT,
    constraints_json TEXT NOT NULL,
    budget_json TEXT NOT NULL,
    plan_json TEXT NOT NULL,
    steps_json TEXT NOT NULL,
    dependencies_json TEXT NOT NULL,
    checkpoints_json TEXT NOT NULL,
    next_action TEXT,
    last_reviewed_at TEXT,
    completion_criteria_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_goals_owner_status ON goals(owner_id, status, priority);

CREATE TABLE IF NOT EXISTS proactive_findings (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL REFERENCES owners(id),
    finding_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    source_events_json TEXT NOT NULL,
    detected_at TEXT NOT NULL,
    recommended_action TEXT,
    auto_action_allowed INTEGER NOT NULL,
    cooldown_seconds INTEGER NOT NULL,
    status TEXT NOT NULL,
    acknowledged_at TEXT,
    last_notified_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_findings_owner_status ON proactive_findings(owner_id, status, detected_at);

CREATE TABLE IF NOT EXISTS personalization (
    owner_id TEXT NOT NULL REFERENCES owners(id),
    key TEXT NOT NULL,
    value_json TEXT NOT NULL,
    source TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(owner_id, key)
);

CREATE TABLE IF NOT EXISTS device_fabric (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL REFERENCES owners(id),
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    transport TEXT NOT NULL,
    status TEXT NOT NULL,
    capabilities_json TEXT NOT NULL,
    trust_level TEXT NOT NULL,
    last_seen TEXT,
    room_id TEXT,
    metadata_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_device_fabric_owner_status ON device_fabric(owner_id, status);
"""


class SQLiteDatabase:
    """Thread-safe local database connection with one explicit schema."""

    def __init__(self, path: str = ":memory:") -> None:
        self.path = path
        if path != ":memory:":
            Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript(SCHEMA)
        self._lock = RLock()
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        if self._closed:
            raise RuntimeError("database is closed")
        with self._lock:
            self.connection.execute("BEGIN")
            try:
                yield self.connection
            except Exception:
                self.connection.rollback()
                raise
            else:
                self.connection.commit()

    def close(self) -> None:
        if not self._closed:
            with self._lock:
                self.connection.close()
                self._closed = True
