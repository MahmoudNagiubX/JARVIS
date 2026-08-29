"""Relational repository operations for authority and runtime state."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from ..events import Event
from .db import SQLiteDatabase
from .models import ConversationRecord, MessageRecord, RunRecord, SessionRecord


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value is not None else None


def parse_time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4()}"


def json_text(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class RuntimeRepository:
    """Single repository boundary; services do not issue SQL directly."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def create_owner(self, display_name: str) -> str:
        owner_id = new_id("owner")
        with self.database.transaction() as db:
            db.execute(
                "INSERT INTO owners(id, display_name, status, created_at) VALUES (?, ?, 'active', ?)",
                (owner_id, display_name, iso(utc_now())),
            )
        return owner_id

    def owner(self, owner_id: str) -> dict[str, Any] | None:
        row = self.database.connection.execute("SELECT * FROM owners WHERE id = ?", (owner_id,)).fetchone()
        return dict(row) if row else None

    def owner_count(self) -> int:
        row = self.database.connection.execute("SELECT COUNT(*) AS count FROM owners").fetchone()
        return int(row["count"])

    def first_owner(self) -> dict[str, Any] | None:
        row = self.database.connection.execute("SELECT * FROM owners ORDER BY created_at, id LIMIT 1").fetchone()
        return dict(row) if row else None

    def create_identity(self, owner_id: str, display_name: str, kind: str, roles: Sequence[str]) -> str:
        identity_id = new_id("identity")
        with self.database.transaction() as db:
            db.execute(
                "INSERT INTO identities VALUES (?, ?, ?, ?, ?, 'active', ?)",
                (identity_id, owner_id, display_name, kind, json_text(list(roles)), iso(utc_now())),
            )
        return identity_id

    def identity(self, identity_id: str) -> dict[str, Any] | None:
        row = self.database.connection.execute(
            "SELECT * FROM identities WHERE id = ? AND status = 'active'", (identity_id,)
        ).fetchone()
        return dict(row) if row else None

    def first_identity(self, owner_id: str) -> dict[str, Any] | None:
        row = self.database.connection.execute(
            "SELECT * FROM identities WHERE owner_id = ? AND status = 'active' ORDER BY created_at, id LIMIT 1",
            (owner_id,),
        ).fetchone()
        return dict(row) if row else None

    def create_enrollment(
        self,
        owner_id: str,
        display_name: str,
        device_kind: str,
        platform: str,
        software_version: str | None,
        code_hash: str,
        scopes: Sequence[str],
        capabilities: Sequence[str],
        expires_at: datetime,
    ) -> tuple[str, datetime]:
        enrollment_id = new_id("enrollment")
        with self.database.transaction() as db:
            db.execute(
                "INSERT INTO enrollments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                (
                    enrollment_id,
                    owner_id,
                    code_hash,
                    display_name,
                    device_kind,
                    platform,
                    software_version,
                    json_text(list(scopes)),
                    json_text(list(capabilities)),
                    iso(expires_at),
                ),
            )
        return enrollment_id, expires_at

    def enrollment_by_hash(self, code_hash: str) -> dict[str, Any] | None:
        row = self.database.connection.execute(
            "SELECT * FROM enrollments WHERE code_hash = ?", (code_hash,)
        ).fetchone()
        return dict(row) if row else None

    def enrollments(self) -> list[dict[str, Any]]:
        rows = self.database.connection.execute("SELECT * FROM enrollments ORDER BY id").fetchall()
        return [dict(row) for row in rows]

    def consume_enrollment(self, enrollment_id: str, consumed_at: datetime) -> None:
        with self.database.transaction() as db:
            db.execute(
                "UPDATE enrollments SET consumed_at = ? WHERE id = ? AND consumed_at IS NULL",
                (iso(consumed_at), enrollment_id),
            )

    def create_device(
        self,
        owner_id: str,
        display_name: str,
        device_kind: str,
        platform: str,
        capabilities: Sequence[str],
        scopes: Sequence[str],
    ) -> str:
        device_id = new_id("device")
        with self.database.transaction() as db:
            db.execute(
                "INSERT INTO devices VALUES (?, ?, ?, ?, ?, ?, ?, 'active', 'enrolled', NULL, NULL)",
                (
                    device_id,
                    owner_id,
                    display_name,
                    device_kind,
                    platform,
                    json_text(sorted(set(capabilities))),
                    json_text(sorted(set(scopes))),
                ),
            )
        return device_id

    def device(self, device_id: str) -> dict[str, Any] | None:
        row = self.database.connection.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
        return dict(row) if row else None

    def first_device(self, owner_id: str) -> dict[str, Any] | None:
        row = self.database.connection.execute(
            "SELECT * FROM devices WHERE owner_id = ? AND status = 'active' ORDER BY id LIMIT 1",
            (owner_id,),
        ).fetchone()
        return dict(row) if row else None

    def devices(self, owner_id: str) -> list[dict[str, Any]]:
        rows = self.database.connection.execute(
            "SELECT * FROM devices WHERE owner_id = ? ORDER BY id", (owner_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    def create_credential(self, device_id: str, public_id: str, secret_hash: str) -> str:
        credential_id = new_id("credential")
        with self.database.transaction() as db:
            db.execute(
                "INSERT INTO credentials VALUES (?, ?, ?, ?, ?, NULL, NULL)",
                (credential_id, device_id, public_id, secret_hash, iso(utc_now())),
            )
        return credential_id

    def credential(self, public_id: str) -> dict[str, Any] | None:
        row = self.database.connection.execute(
            "SELECT * FROM credentials WHERE public_id = ?", (public_id,)
        ).fetchone()
        return dict(row) if row else None

    def touch_device(self, device_id: str, credential_id: str, timestamp: datetime) -> None:
        with self.database.transaction() as db:
            db.execute("UPDATE devices SET last_seen_at = ? WHERE id = ?", (iso(timestamp), device_id))
            db.execute(
                "UPDATE credentials SET last_used_at = ? WHERE id = ?",
                (iso(timestamp), credential_id),
            )

    def revoke_device(self, device_id: str, timestamp: datetime) -> None:
        with self.database.transaction() as db:
            db.execute(
                "UPDATE devices SET status = 'revoked', revoked_at = ? WHERE id = ?",
                (iso(timestamp), device_id),
            )
            db.execute(
                "UPDATE credentials SET revoked_at = ? WHERE device_id = ?",
                (iso(timestamp), device_id),
            )

    def create_session(self, owner_id: str, device_id: str) -> SessionRecord:
        now = utc_now()
        record = SessionRecord(new_id("session"), owner_id, device_id, "active", now, now, None)
        with self.database.transaction() as db:
            db.execute(
                "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, NULL)",
                (record.id, record.owner_id, record.device_id, record.status, iso(now), iso(now)),
            )
        return record

    def session(self, session_id: str) -> SessionRecord | None:
        row = self.database.connection.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            return None
        return SessionRecord(
            row["id"], row["owner_id"], row["device_id"], row["status"],
            parse_time(row["created_at"]), parse_time(row["last_seen_at"]), parse_time(row["closed_at"]),
        )

    def close_session(self, session_id: str) -> None:
        with self.database.transaction() as db:
            db.execute(
                "UPDATE sessions SET status = 'closed', closed_at = ?, last_seen_at = ? WHERE id = ?",
                (iso(utc_now()), iso(utc_now()), session_id),
            )

    def create_conversation(self, owner_id: str, device_id: str, title: str | None) -> ConversationRecord:
        now = utc_now()
        record = ConversationRecord(new_id("conversation"), owner_id, device_id, title, "active", now, now, None)
        with self.database.transaction() as db:
            db.execute(
                "INSERT INTO conversations VALUES (?, ?, ?, ?, 'active', ?, ?, NULL)",
                (record.id, owner_id, device_id, title, iso(now), iso(now)),
            )
        return record

    def conversation(self, conversation_id: str) -> ConversationRecord | None:
        row = self.database.connection.execute(
            "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        if row is None:
            return None
        return ConversationRecord(
            row["id"], row["owner_id"], row["created_by_device_id"], row["title"], row["status"],
            parse_time(row["created_at"]), parse_time(row["updated_at"]), parse_time(row["last_message_at"]),
        )

    def message_by_client_id(self, client_message_id: str) -> MessageRecord | None:
        row = self.database.connection.execute(
            "SELECT * FROM messages WHERE client_message_id = ?", (client_message_id,)
        ).fetchone()
        return self._message(row) if row else None

    def create_message(
        self,
        conversation_id: str,
        session_id: str | None,
        run_id: str | None,
        author_device_id: str | None,
        role: str,
        content: str,
        client_message_id: str | None = None,
    ) -> MessageRecord:
        row = self.database.connection.execute(
            "SELECT COALESCE(MAX(ordinal), 0) + 1 AS next_ordinal FROM messages WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()
        now = utc_now()
        record = MessageRecord(
            new_id("message"), conversation_id, session_id, run_id, author_device_id, role,
            content, int(row["next_ordinal"]), client_message_id, now,
        )
        with self.database.transaction() as db:
            db.execute(
                "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (record.id, record.conversation_id, record.session_id, record.run_id,
                 record.author_device_id, record.role, record.content, record.ordinal,
                 record.client_message_id, iso(record.created_at)),
            )
            db.execute(
                "UPDATE conversations SET updated_at = ?, last_message_at = ? WHERE id = ?",
                (iso(now), iso(now), conversation_id),
            )
        return record

    def messages(self, conversation_id: str) -> list[MessageRecord]:
        rows = self.database.connection.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY ordinal", (conversation_id,)
        ).fetchall()
        return [self._message(row) for row in rows]

    def update_message_run_id(self, message_id: str, run_id: str) -> None:
        with self.database.transaction() as db:
            db.execute("UPDATE messages SET run_id = ? WHERE id = ?", (run_id, message_id))

    @staticmethod
    def _message(row: sqlite3.Row) -> MessageRecord:
        return MessageRecord(
            row["id"], row["conversation_id"], row["session_id"], row["run_id"],
            row["author_device_id"], row["role"], row["content"], row["ordinal"],
            row["client_message_id"], parse_time(row["created_at"]),
        )

    def create_run(
        self,
        conversation_id: str,
        session_id: str,
        device_id: str,
        trigger_message_id: str,
        correlation_id: str,
    ) -> RunRecord:
        now = utc_now()
        run = RunRecord(
            new_id("run"), conversation_id, session_id, device_id, trigger_message_id, "queued",
            now, None, None, None, None, None, None, None, None, None, None, None, None,
            correlation_id, {}, False, None,
        )
        with self.database.transaction() as db:
            db.execute(
                "INSERT INTO runs(id, conversation_id, session_id, request_device_id, trigger_message_id, status, created_at, correlation_id, context_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (run.id, conversation_id, session_id, device_id, trigger_message_id, run.status, iso(now), correlation_id, "{}"),
            )
        return run

    def run(self, run_id: str) -> RunRecord | None:
        row = self.database.connection.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return self._run(row) if row else None

    @staticmethod
    def _run(row: sqlite3.Row) -> RunRecord:
        return RunRecord(
            row["id"], row["conversation_id"], row["session_id"], row["request_device_id"],
            row["trigger_message_id"], row["status"], parse_time(row["created_at"]),
            parse_time(row["started_at"]), parse_time(row["cancel_requested_at"]),
            parse_time(row["completed_at"]), row["model_request_id"], row["model_id"],
            row["model_digest"], row["finish_reason"], row["prompt_usage"], row["output_usage"],
            row["latency_ms"], row["failure_category"], row["failure_code"], row["correlation_id"],
            json.loads(row["context_json"]), bool(row["context_truncated"]), row["pending_approval_id"],
        )

    def update_run(self, run_id: str, **fields: object) -> RunRecord:
        allowed = {
            "status", "started_at", "cancel_requested_at", "completed_at", "model_request_id",
            "model_id", "model_digest", "finish_reason", "prompt_usage", "output_usage",
            "latency_ms", "failure_category", "failure_code", "context_json", "context_truncated",
            "pending_approval_id",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"unsupported run fields: {sorted(unknown)}")
        assignments = ", ".join(f"{key} = ?" for key in fields)
        values = [json_text(value) if key == "context_json" and not isinstance(value, str) else value for key, value in fields.items()]
        values = [iso(value) if isinstance(value, datetime) else value for value in values]
        with self.database.transaction() as db:
            db.execute(f"UPDATE runs SET {assignments} WHERE id = ?", (*values, run_id))
        result = self.run(run_id)
        if result is None:
            raise KeyError(run_id)
        return result

    def append_event(self, event: Event) -> int:
        with self.database.transaction() as db:
            cursor = db.execute(
                "INSERT INTO events(event_id, event_type, category, timestamp, correlation_id, causation_id, session_id, actor_id, payload_json, severity, state) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (event.event_id, event.event_type, event.category.value, iso(event.timestamp), event.correlation_id,
                 event.causation_id, event.session_id, event.actor_id, json_text(dict(event.payload)),
                 event.severity.value, event.state.value),
            )
            return int(cursor.lastrowid)

    def events(self, correlation_id: str | None = None) -> list[dict[str, Any]]:
        if correlation_id is None:
            rows = self.database.connection.execute("SELECT * FROM events ORDER BY sequence").fetchall()
        else:
            rows = self.database.connection.execute(
                "SELECT * FROM events WHERE correlation_id = ? ORDER BY sequence", (correlation_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    def insert_approval(self, request: Any, status: str) -> None:
        with self.database.transaction() as db:
            db.execute(
                "INSERT INTO approvals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)",
                (request.approval_id, request.action, request.requester_id, request.device_id, request.reason,
                 iso(request.created_at), iso(request.expires_at), json_text(dict(request.preview)), status),
            )

    def approval(self, approval_id: str) -> dict[str, Any] | None:
        row = self.database.connection.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        return dict(row) if row else None

    def pending_approvals(self, owner_id: str | None = None) -> list[dict[str, Any]]:
        if owner_id is None:
            rows = self.database.connection.execute(
                "SELECT * FROM approvals WHERE status = 'pending' ORDER BY created_at"
            ).fetchall()
        else:
            rows = self.database.connection.execute(
                "SELECT * FROM approvals WHERE status = 'pending' AND requester_id = ? ORDER BY created_at",
                (owner_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_approval(self, approval_id: str, status: str, decided_by: str, decided_at: datetime, reason: str | None) -> None:
        with self.database.transaction() as db:
            db.execute(
                "UPDATE approvals SET status = ?, decided_by = ?, decided_at = ?, decision_reason = ? WHERE id = ? AND status = 'pending'",
                (status, decided_by, iso(decided_at), reason, approval_id),
            )

    def insert_audit(self, record: Any) -> None:
        with self.database.transaction() as db:
            db.execute(
                "INSERT INTO audit_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (record.record_id, record.event_type, iso(record.occurred_at), record.actor_id, record.device_id,
                 record.correlation_id, record.outcome, record.reason_code, json_text(dict(record.metadata))),
            )

    def audit(self, correlation_id: str | None = None) -> list[dict[str, Any]]:
        if correlation_id is None:
            rows = self.database.connection.execute("SELECT * FROM audit_records ORDER BY occurred_at").fetchall()
        else:
            rows = self.database.connection.execute(
                "SELECT * FROM audit_records WHERE correlation_id = ? ORDER BY occurred_at", (correlation_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    def insert_tool_call(self, tool_call_id: str, run_id: str | None, name: str, arguments: Mapping[str, Any], digest: str, status: str, approval_id: str | None = None) -> None:
        with self.database.transaction() as db:
            db.execute(
                "INSERT INTO tool_calls(id, run_id, name, arguments_json, argument_digest, status, approval_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (tool_call_id, run_id, name, json_text(dict(arguments)), digest, status, approval_id, iso(utc_now())),
            )

    def tool_call(self, tool_call_id: str) -> dict[str, Any] | None:
        row = self.database.connection.execute("SELECT * FROM tool_calls WHERE id = ?", (tool_call_id,)).fetchone()
        return dict(row) if row else None

    def tool_call_by_approval(self, approval_id: str) -> dict[str, Any] | None:
        row = self.database.connection.execute(
            "SELECT * FROM tool_calls WHERE approval_id = ?", (approval_id,)
        ).fetchone()
        return dict(row) if row else None

    def set_tool_call_approval(self, tool_call_id: str, approval_id: str) -> None:
        with self.database.transaction() as db:
            db.execute("UPDATE tool_calls SET approval_id = ? WHERE id = ?", (approval_id, tool_call_id))

    def update_tool_call(self, tool_call_id: str, status: str, output: object = None) -> None:
        with self.database.transaction() as db:
            db.execute(
                "UPDATE tool_calls SET status = ?, output_json = ?, completed_at = ? WHERE id = ?",
                (status, json_text(output) if output is not None else None, iso(utc_now()), tool_call_id),
            )

    # Phase 03 memory -----------------------------------------------------
    def insert_memory(self, record: Any) -> None:
        updated_at = record.updated_at or record.created_at
        with self.database.transaction() as db:
            db.execute(
                "INSERT INTO memories VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.memory_id,
                    record.owner_id,
                    record.category,
                    record.content,
                    json_text(dict(record.metadata)),
                    json_text(dict(record.structured_data)),
                    record.source,
                    record.source_reference,
                    iso(record.created_at),
                    iso(updated_at),
                    iso(record.last_accessed_at),
                    float(record.confidence),
                    record.sensitivity,
                    record.scope,
                    iso(record.valid_from),
                    iso(record.valid_until),
                    record.retention_policy,
                    record.status,
                    record.supersedes,
                    json_text(list(record.tags)),
                    int(record.pinned),
                    int(record.archived),
                    json_text(list(record.embedding)) if record.embedding is not None else None,
                ),
            )

    def memory(self, owner_id: str, memory_id: str) -> dict[str, Any] | None:
        row = self.database.connection.execute(
            "SELECT * FROM memories WHERE owner_id = ? AND id = ?", (owner_id, memory_id)
        ).fetchone()
        return dict(row) if row else None

    def memories(
        self,
        owner_id: str,
        statuses: Sequence[str] = ("active",),
        include_archived: bool = False,
        category: str | None = None,
        source: str | None = None,
        tags: Sequence[str] = (),
    ) -> list[dict[str, Any]]:
        placeholders = ",".join("?" for _ in statuses)
        archived_clause = "" if include_archived else " AND archived = 0"
        conditions = ["owner_id = ?"]
        values: list[object] = [owner_id]
        if statuses:
            conditions.append(f"status IN ({placeholders})")
            values.extend(statuses)
        if category:
            conditions.append("category = ?")
            values.append(category)
        if source:
            conditions.append("source = ?")
            values.append(source)
        if tags:
            conditions.extend("tags_json LIKE ?" for _ in tags)
            values.extend(f'%"{tag}"%' for tag in tags)
        rows = self.database.connection.execute(
            f"SELECT * FROM memories WHERE {' AND '.join(conditions)}{archived_clause} ORDER BY pinned DESC, updated_at DESC",
            values,
        ).fetchall()
        return [dict(row) for row in rows]

    def update_memory(self, owner_id: str, memory_id: str, **fields: object) -> dict[str, Any]:
        allowed = {
            "category", "content", "structured_data_json", "source", "source_reference",
            "updated_at", "last_accessed_at", "confidence", "sensitivity", "scope",
            "valid_from", "valid_until", "retention_policy", "status", "supersedes",
            "tags_json", "pinned", "archived", "embedding_json",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"unsupported memory fields: {sorted(unknown)}")
        assignments = ", ".join(f"{key} = ?" for key in fields)
        values = [iso(value) if isinstance(value, datetime) else value for value in fields.values()]
        with self.database.transaction() as db:
            db.execute(
                f"UPDATE memories SET {assignments} WHERE owner_id = ? AND id = ?",
                (*values, owner_id, memory_id),
            )
        result = self.memory(owner_id, memory_id)
        if result is None:
            raise KeyError(memory_id)
        return result

    # Phase 03 world state -----------------------------------------------
    def insert_world_observation(self, observation: Any, owner_id: str) -> None:
        with self.database.transaction() as db:
            db.execute(
                "INSERT INTO world_observations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    observation.observation_id,
                    observation.owner_id or owner_id,
                    observation.source,
                    observation.source_reference,
                    iso(observation.observed_at),
                    observation.subject,
                    json_text(dict(observation.value)),
                    float(observation.confidence),
                    observation.freshness_seconds,
                    iso(observation.expires_at),
                    int(observation.authority_level),
                    observation.conflict_state,
                    observation.device_id,
                    observation.scope,
                ),
            )

    def world_observations(self, owner_id: str, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.database.connection.execute(
            "SELECT * FROM world_observations WHERE owner_id = ? ORDER BY observed_at DESC LIMIT ?",
            (owner_id, max(1, min(limit, 1000))),
        ).fetchall()
        return [dict(row) for row in rows]

    def world_fact(self, owner_id: str, key: str) -> dict[str, Any] | None:
        row = self.database.connection.execute(
            "SELECT * FROM world_facts WHERE owner_id = ? AND key = ? ORDER BY authority_level DESC, observed_at DESC LIMIT 1",
            (owner_id, key),
        ).fetchone()
        return dict(row) if row else None

    def world_facts(self, owner_id: str, key_prefix: str | None = None, include_expired: bool = False) -> list[dict[str, Any]]:
        conditions = ["owner_id = ?"]
        values: list[object] = [owner_id]
        if key_prefix:
            conditions.append("key LIKE ?")
            values.append(f"{key_prefix}%")
        if not include_expired:
            conditions.append("(expires_at IS NULL OR expires_at > ?)")
            values.append(iso(utc_now()))
        rows = self.database.connection.execute(
            f"SELECT * FROM world_facts WHERE {' AND '.join(conditions)} ORDER BY key", values
        ).fetchall()
        return [dict(row) for row in rows]

    def insert_world_fact(self, fact: Any) -> None:
        with self.database.transaction() as db:
            db.execute(
                "INSERT INTO world_facts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    fact.fact_id, fact.owner_id, fact.key, json_text(fact.value), fact.source,
                    fact.source_reference, iso(fact.observed_at), fact.freshness, iso(fact.expires_at),
                    float(fact.confidence), int(fact.authority_level), fact.conflict_state,
                    fact.device_id, fact.scope,
                ),
            )

    def update_world_fact(self, fact_id: str, **fields: object) -> None:
        allowed = {"value_json", "source", "source_reference", "observed_at", "freshness", "expires_at", "confidence", "authority_level", "conflict_state", "device_id", "scope"}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"unsupported world fact fields: {sorted(unknown)}")
        assignments = ", ".join(f"{key} = ?" for key in fields)
        values = [iso(value) if isinstance(value, datetime) else value for value in fields.values()]
        with self.database.transaction() as db:
            db.execute(f"UPDATE world_facts SET {assignments} WHERE id = ?", (*values, fact_id))

    def insert_world_conflict(self, conflict: Any) -> None:
        with self.database.transaction() as db:
            db.execute(
                "INSERT INTO world_conflicts VALUES (?, ?, ?, ?, ?, ?, ?)",
                (conflict.conflict_id, conflict.owner_id, conflict.key, json_text(list(conflict.fact_ids)), conflict.reason, iso(conflict.detected_at), int(conflict.resolved)),
            )

    def world_conflicts(self, owner_id: str, unresolved_only: bool = True) -> list[dict[str, Any]]:
        condition = " AND resolved = 0" if unresolved_only else ""
        rows = self.database.connection.execute(
            f"SELECT * FROM world_conflicts WHERE owner_id = ?{condition} ORDER BY detected_at DESC", (owner_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    # Phase 03 goals ------------------------------------------------------
    def insert_goal(self, goal: Any) -> None:
        with self.database.transaction() as db:
            db.execute(
                "INSERT INTO goals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    goal.goal_id, goal.owner_id, goal.title or goal.statement[:120], goal.description or goal.statement,
                    goal.status.value if hasattr(goal.status, "value") else goal.status, goal.priority,
                    iso(goal.created_at), iso(goal.target_date), json_text(dict(goal.constraints)), json_text(dict(goal.budget)),
                    json_text(list(goal.plan)), json_text(list(goal.steps)), json_text(list(goal.dependencies)),
                    json_text(list(goal.checkpoints)), goal.next_action, iso(goal.last_reviewed_at),
                    json_text(list(goal.completion_criteria)), json_text(dict(goal.metadata)),
                ),
            )

    def goal(self, owner_id: str, goal_id: str) -> dict[str, Any] | None:
        row = self.database.connection.execute("SELECT * FROM goals WHERE owner_id = ? AND id = ?", (owner_id, goal_id)).fetchone()
        return dict(row) if row else None

    def goals(self, owner_id: str, statuses: Sequence[str] = ()) -> list[dict[str, Any]]:
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            rows = self.database.connection.execute(
                f"SELECT * FROM goals WHERE owner_id = ? AND status IN ({placeholders}) ORDER BY priority DESC, created_at DESC",
                (owner_id, *statuses),
            ).fetchall()
        else:
            rows = self.database.connection.execute(
                "SELECT * FROM goals WHERE owner_id = ? ORDER BY priority DESC, created_at DESC", (owner_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    def update_goal(self, owner_id: str, goal_id: str, **fields: object) -> dict[str, Any]:
        allowed = {"title", "description", "status", "priority", "target_date", "constraints_json", "budget_json", "plan_json", "steps_json", "dependencies_json", "checkpoints_json", "next_action", "last_reviewed_at", "completion_criteria_json", "metadata_json"}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"unsupported goal fields: {sorted(unknown)}")
        assignments = ", ".join(f"{key} = ?" for key in fields)
        values = [iso(value) if isinstance(value, datetime) else value for value in fields.values()]
        with self.database.transaction() as db:
            db.execute(f"UPDATE goals SET {assignments} WHERE owner_id = ? AND id = ?", (*values, owner_id, goal_id))
        result = self.goal(owner_id, goal_id)
        if result is None:
            raise KeyError(goal_id)
        return result

    # Phase 03 proactive and personalization ----------------------------
    def insert_finding(self, finding: Any) -> None:
        with self.database.transaction() as db:
            db.execute(
                "INSERT INTO proactive_findings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    finding.finding_id, finding.owner_id, finding.finding_type, finding.severity,
                    json_text(dict(finding.evidence)), json_text(list(finding.source_events)), iso(finding.detected_at),
                    finding.recommended_action, int(finding.auto_action_allowed), finding.cooldown_seconds,
                    finding.status, iso(finding.acknowledged_at), iso(finding.last_notified_at),
                ),
            )

    def finding(self, owner_id: str, finding_id: str) -> dict[str, Any] | None:
        row = self.database.connection.execute("SELECT * FROM proactive_findings WHERE owner_id = ? AND id = ?", (owner_id, finding_id)).fetchone()
        return dict(row) if row else None

    def findings(self, owner_id: str, statuses: Sequence[str] = ()) -> list[dict[str, Any]]:
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            rows = self.database.connection.execute(
                f"SELECT * FROM proactive_findings WHERE owner_id = ? AND status IN ({placeholders}) ORDER BY detected_at DESC",
                (owner_id, *statuses),
            ).fetchall()
        else:
            rows = self.database.connection.execute(
                "SELECT * FROM proactive_findings WHERE owner_id = ? ORDER BY detected_at DESC", (owner_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    def update_finding(self, owner_id: str, finding_id: str, **fields: object) -> dict[str, Any]:
        allowed = {"status", "acknowledged_at", "last_notified_at"}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"unsupported finding fields: {sorted(unknown)}")
        assignments = ", ".join(f"{key} = ?" for key in fields)
        values = [iso(value) if isinstance(value, datetime) else value for value in fields.values()]
        with self.database.transaction() as db:
            db.execute(f"UPDATE proactive_findings SET {assignments} WHERE owner_id = ? AND id = ?", (*values, owner_id, finding_id))
        result = self.finding(owner_id, finding_id)
        if result is None:
            raise KeyError(finding_id)
        return result

    def set_personalization(self, owner_id: str, key: str, value: object, source: str, updated_at: datetime | None = None) -> None:
        with self.database.transaction() as db:
            db.execute(
                "INSERT INTO personalization(owner_id, key, value_json, source, updated_at) VALUES (?, ?, ?, ?, ?) ON CONFLICT(owner_id, key) DO UPDATE SET value_json = excluded.value_json, source = excluded.source, updated_at = excluded.updated_at",
                (owner_id, key, json_text(value), source, iso(updated_at or utc_now())),
            )

    def personalization(self, owner_id: str) -> list[dict[str, Any]]:
        rows = self.database.connection.execute("SELECT * FROM personalization WHERE owner_id = ? ORDER BY key", (owner_id,)).fetchall()
        return [dict(row) for row in rows]

    def delete_personalization(self, owner_id: str, key: str) -> None:
        with self.database.transaction() as db:
            db.execute("DELETE FROM personalization WHERE owner_id = ? AND key = ?", (owner_id, key))
