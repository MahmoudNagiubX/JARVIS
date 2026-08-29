CREATE TABLE IF NOT EXISTS workspace_projects (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    repo_path TEXT NOT NULL,
    project_type TEXT NOT NULL,
    approved INTEGER NOT NULL DEFAULT 1,
    metadata_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(owner_id, repo_path)
);
CREATE INDEX IF NOT EXISTS idx_workspace_projects_owner ON workspace_projects(owner_id, updated_at);
