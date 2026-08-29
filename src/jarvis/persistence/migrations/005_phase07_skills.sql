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
