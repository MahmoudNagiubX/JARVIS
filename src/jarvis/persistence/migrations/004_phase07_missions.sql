-- Phase 07 bounded missions are layered above, and never replace, goals.
CREATE TABLE IF NOT EXISTS missions (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
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
CREATE TABLE IF NOT EXISTS mission_evidence (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(id),
    kind TEXT NOT NULL,
    locator TEXT NOT NULL,
    details_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
