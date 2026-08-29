CREATE TABLE IF NOT EXISTS communication_insights (
    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, thread_id TEXT NOT NULL, insight_json TEXT NOT NULL,
    created_at TEXT NOT NULL, UNIQUE(owner_id, thread_id)
);
CREATE TABLE IF NOT EXISTS worker_delegations (
    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, worker TEXT NOT NULL, reason TEXT NOT NULL, scope TEXT,
    task TEXT NOT NULL, result_json TEXT NOT NULL, started_at TEXT NOT NULL, completed_at TEXT
);
