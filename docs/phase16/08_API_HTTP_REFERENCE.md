# Phase 16: API HTTP Reference

All personal intelligence endpoints are authenticated through the local HTTP server (`src/jarvis/api/http.py`).

## 1. Memory Endpoints

### `GET /memory`
Query active memory records.
- **Parameters**: `q` (search text), `category`, `source`, `tag`, `include_archived` (bool), `limit` (int, default 50).
- **Response**: `{"memories": [MemoryRecord, ...]}`

### `POST /memory`
Create a new memory record through policy evaluation.
- **Body**: `{"content": str, "category": str, "structured_data": dict, "source": str, "source_reference": str, "confidence": float, "sensitivity": str, "tags": list[str]}`
- **Response**: `201 Created` with created `MemoryRecord`.

### `GET /memory/{id}`
Retrieve specific memory record by UUID.
- **Response**: `MemoryRecord` or `404 Not Found`.

### `PATCH /memory/{id}`
Update content, category, structured data, sensitivity, or tags.
- **Body**: `{"content": str, ...}`
- **Response**: Updated `MemoryRecord`.

### `DELETE /memory/{id}`
Soft-delete memory record (`status="deleted"`, `archived=1`). Excludes from all future search/recall.
- **Response**: `200 OK`

### `POST /memory/{id}/pin`
Pin or unpin a memory record.
- **Body**: `{"enabled": bool}`
- **Response**: Updated `MemoryRecord`.

### `POST /memory/{id}/archive`
Archive or unarchive a memory record.
- **Body**: `{"enabled": bool}`
- **Response**: Updated `MemoryRecord`.

### `POST /memory/forget-category`
Bulk delete all memories in a given category.
- **Body**: `{"category": str}`
- **Response**: `{"deleted": int, "category": str}`

## 2. World State Endpoints

### `GET /world-state`
Fetch current authoritative snapshot of fresh facts.
- **Parameters**: `key_prefix`, `include_expired` (bool).
- **Response**: `{"facts": [WorldStateFact, ...], "snapshot_id": str, ...}`

### `GET /world-state/conflicts`
Fetch active competing observation conflicts.
- **Response**: `{"conflicts": [WorldStateConflict, ...]}`

## 3. Goals & Missions Endpoints

### `GET /goals`
List owner goals filtered by status.
- **Parameters**: `status` (repeated query param).
- **Response**: `{"goals": [Goal, ...]}`

### `POST /goals`
Create a new goal.
- **Body**: Goal payload.
- **Response**: `201 Created` with `Goal`.

### `GET /missions`
List active and past missions.
- **Response**: `{"missions": [Mission, ...]}`

### `POST /missions`
Create and start a mission.
- **Body**: `{"title": str, "request": str, "budget": dict}`
- **Response**: `201 Created` with `Mission`.

## 4. Proactivity & Automation Endpoints

### `GET /proactive/findings`
List proactive findings.
- **Parameters**: `active_only` (bool).
- **Response**: `{"findings": [ProactiveFinding, ...]}`

### `POST /proactive/findings/{id}/acknowledge`
Acknowledge finding.
- **Response**: `200 OK` with updated `ProactiveFinding`.

### `GET /automations`
List configured automation rules.
- **Response**: `{"automations": [AutomationRule, ...]}`
