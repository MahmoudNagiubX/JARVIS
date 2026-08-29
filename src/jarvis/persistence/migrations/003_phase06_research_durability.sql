-- Phase 06 durable research ledger. SQLite's bootstrap schema mirrors these
-- tables; PostgreSQL deployment tooling applies equivalent typed tables.
CREATE TABLE IF NOT EXISTS research_runs (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
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
