CREATE TABLE IF NOT EXISTS intelligence_findings (
    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, finding_type TEXT NOT NULL, severity TEXT NOT NULL,
    evidence_json TEXT NOT NULL, baseline_json TEXT NOT NULL, current_value_json TEXT NOT NULL,
    confidence REAL NOT NULL, detected_at TEXT NOT NULL, affected_resource TEXT NOT NULL,
    recommended_action TEXT NOT NULL, auto_action_allowed INTEGER NOT NULL, cooldown_seconds REAL NOT NULL,
    status TEXT NOT NULL, fingerprint TEXT NOT NULL, resolved_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_intelligence_findings_owner ON intelligence_findings(owner_id, status, detected_at);
CREATE TABLE IF NOT EXISTS briefings (
    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, briefing_type TEXT NOT NULL, title TEXT NOT NULL,
    summary TEXT NOT NULL, items_json TEXT NOT NULL, evidence_ids_json TEXT NOT NULL, created_at TEXT NOT NULL,
    delivered_at TEXT, dismissed_at TEXT, dedup_key TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS automation_rules (
    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, name TEXT NOT NULL, enabled INTEGER NOT NULL,
    trigger_json TEXT NOT NULL, conditions_json TEXT NOT NULL, actions_json TEXT NOT NULL, risk_level TEXT NOT NULL,
    cooldown_seconds REAL NOT NULL, last_run_at TEXT, next_run_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS automation_runs (
    id TEXT PRIMARY KEY, rule_id TEXT NOT NULL, status TEXT NOT NULL, trigger_event_id TEXT,
    result_json TEXT NOT NULL, started_at TEXT NOT NULL, completed_at TEXT
);
CREATE TABLE IF NOT EXISTS evaluation_runs (
    id TEXT PRIMARY KEY, owner_id TEXT, suite TEXT NOT NULL, status TEXT NOT NULL, passed INTEGER NOT NULL,
    regression INTEGER NOT NULL, summary TEXT NOT NULL, results_json TEXT NOT NULL, started_at TEXT NOT NULL, completed_at TEXT
);
