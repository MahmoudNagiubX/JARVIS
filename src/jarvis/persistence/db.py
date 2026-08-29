"""SQLite persistence adapter used for local durability and offline tests.

The domain only depends on repositories. SQLite is the zero-install local
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

CREATE TABLE IF NOT EXISTS research_runs (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL REFERENCES owners(id),
    device_id TEXT NOT NULL,
    query TEXT NOT NULL,
    status TEXT NOT NULL,
    plan_json TEXT NOT NULL,
    steps_json TEXT NOT NULL,
    context_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    error_code TEXT,
    report_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_research_runs_owner_status ON research_runs(owner_id, status, created_at);

CREATE TABLE IF NOT EXISTS research_sources (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES research_runs(id),
    locator TEXT NOT NULL,
    title TEXT NOT NULL,
    source_type TEXT NOT NULL,
    retrieved_at TEXT,
    fingerprint TEXT,
    trust TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_research_sources_run ON research_sources(run_id);

CREATE TABLE IF NOT EXISTS research_evidence (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES research_runs(id),
    source_id TEXT NOT NULL,
    excerpt TEXT NOT NULL,
    locator TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    untrusted_content INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_research_evidence_run ON research_evidence(run_id);

CREATE TABLE IF NOT EXISTS missions (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL REFERENCES owners(id),
    goal_id TEXT,
    request TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    plan_json TEXT,
    budget_json TEXT NOT NULL,
    current_step INTEGER NOT NULL,
    tool_calls INTEGER NOT NULL,
    worker_runs INTEGER NOT NULL,
    external_actions INTEGER NOT NULL,
    replan_count INTEGER NOT NULL,
    blocked_reason TEXT,
    approval_id TEXT,
    result_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_missions_owner_status ON missions(owner_id, status, updated_at);

CREATE TABLE IF NOT EXISTS mission_checkpoints (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(id),
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_mission_checkpoints_mission ON mission_checkpoints(mission_id, created_at);

CREATE TABLE IF NOT EXISTS mission_evidence (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(id),
    kind TEXT NOT NULL,
    locator TEXT NOT NULL,
    details_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mission_evidence_mission ON mission_evidence(mission_id, created_at);

CREATE TABLE IF NOT EXISTS skills (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    category TEXT NOT NULL,
    status TEXT NOT NULL,
    current_version TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS skill_versions (
    id TEXT PRIMARY KEY,
    skill_id TEXT NOT NULL REFERENCES skills(id),
    version TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    source TEXT NOT NULL,
    change_reason TEXT NOT NULL,
    previous_version TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(skill_id, version)
);
CREATE TABLE IF NOT EXISTS skill_executions (
    id TEXT PRIMARY KEY,
    skill_id TEXT NOT NULL,
    owner_id TEXT NOT NULL REFERENCES owners(id),
    identity_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    current_step INTEGER NOT NULL,
    status TEXT NOT NULL,
    approval_id TEXT,
    correlation_id TEXT NOT NULL,
    values_json TEXT NOT NULL,
    results_json TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    error_code TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_skill_executions_owner ON skill_executions(owner_id, updated_at);
CREATE TABLE IF NOT EXISTS workspace_projects (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL REFERENCES owners(id),
    repo_path TEXT NOT NULL,
    project_type TEXT NOT NULL,
    approved INTEGER NOT NULL DEFAULT 1,
    metadata_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(owner_id, repo_path)
);
CREATE INDEX IF NOT EXISTS idx_workspace_projects_owner ON workspace_projects(owner_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_skill_versions_skill ON skill_versions(skill_id, created_at);
CREATE TABLE IF NOT EXISTS intelligence_findings (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL REFERENCES owners(id),
    finding_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    baseline_json TEXT NOT NULL,
    current_value_json TEXT NOT NULL,
    confidence REAL NOT NULL,
    detected_at TEXT NOT NULL,
    affected_resource TEXT NOT NULL,
    recommended_action TEXT NOT NULL,
    auto_action_allowed INTEGER NOT NULL,
    cooldown_seconds REAL NOT NULL,
    status TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    resolved_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_intelligence_findings_owner ON intelligence_findings(owner_id, status, detected_at);
CREATE TABLE IF NOT EXISTS briefings (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL REFERENCES owners(id),
    briefing_type TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    items_json TEXT NOT NULL,
    evidence_ids_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    delivered_at TEXT,
    dismissed_at TEXT,
    dedup_key TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_briefings_owner ON briefings(owner_id, created_at);
CREATE TABLE IF NOT EXISTS automation_rules (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL REFERENCES owners(id),
    name TEXT NOT NULL,
    enabled INTEGER NOT NULL,
    trigger_json TEXT NOT NULL,
    conditions_json TEXT NOT NULL,
    actions_json TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    cooldown_seconds REAL NOT NULL,
    last_run_at TEXT,
    next_run_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS automation_runs (
    id TEXT PRIMARY KEY,
    rule_id TEXT NOT NULL REFERENCES automation_rules(id),
    status TEXT NOT NULL,
    trigger_event_id TEXT,
    result_json TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE TABLE IF NOT EXISTS automation_bindings (
    id TEXT PRIMARY KEY,
    rule_id TEXT NOT NULL UNIQUE REFERENCES automation_rules(id),
    owner_id TEXT NOT NULL REFERENCES owners(id),
    identity_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    service_principal TEXT NOT NULL,
    scopes_json TEXT NOT NULL,
    capabilities_json TEXT NOT NULL,
    created_by TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_automation_bindings_owner ON automation_bindings(owner_id, enabled);
CREATE INDEX IF NOT EXISTS idx_automation_rules_owner ON automation_rules(owner_id, enabled, updated_at);
CREATE INDEX IF NOT EXISTS idx_automation_runs_rule ON automation_runs(rule_id, started_at);
CREATE TABLE IF NOT EXISTS evaluation_runs (
    id TEXT PRIMARY KEY,
    owner_id TEXT,
    suite TEXT NOT NULL,
    status TEXT NOT NULL,
    passed INTEGER NOT NULL,
    regression INTEGER NOT NULL,
    summary TEXT NOT NULL,
    results_json TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_evaluation_runs_suite ON evaluation_runs(suite, started_at);
CREATE TABLE IF NOT EXISTS communication_insights (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL REFERENCES owners(id),
    thread_id TEXT NOT NULL,
    insight_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(owner_id, thread_id)
);
CREATE TABLE IF NOT EXISTS worker_delegations (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL REFERENCES owners(id),
    worker TEXT NOT NULL,
    reason TEXT NOT NULL,
    scope TEXT,
    task TEXT NOT NULL,
    result_json TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT
);
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
