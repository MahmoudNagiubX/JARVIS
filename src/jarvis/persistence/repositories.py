"""Relational repository operations for authority and runtime state."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
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
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


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

    def reconcile_active_runs(self) -> int:
        """Fail only process-owned transient runs after an unclean restart."""
        with self.database.transaction() as db:
            cursor = db.execute(
                "UPDATE runs SET status = 'failed', completed_at = ?, failure_code = 'process_restarted' WHERE status IN ('queued', 'running', 'cancel_requested')",
                (iso(utc_now()),),
            )
            return int(cursor.rowcount)

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

    def event_count(self) -> int:
        row = self.database.connection.execute("SELECT COUNT(*) AS count FROM events").fetchone()
        return int(row["count"])

    def prune_events(self, before: datetime, *, dry_run: bool = True) -> dict[str, object]:
        """Prune only the operational event log; authority records stay intact.

        The default is a dry run so retention cannot silently remove evidence.
        Memories, conversations, goals, identities, and audit_records are never
        touched by this method.
        """

        cutoff = iso(before)
        row = self.database.connection.execute(
            "SELECT COUNT(*) AS count FROM events WHERE timestamp < ?", (cutoff,)
        ).fetchone()
        matched = int(row["count"])
        deleted = 0
        if not dry_run and matched:
            with self.database.transaction() as db:
                cursor = db.execute("DELETE FROM events WHERE timestamp < ?", (cutoff,))
                deleted = int(cursor.rowcount)
        return {"before": cutoff, "matched": matched, "deleted": deleted, "dry_run": dry_run}

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

    # Phase 06 durable research jobs -------------------------------------
    def insert_research_run(self, run: Any) -> None:
        with self.database.transaction() as db:
            db.execute(
                "INSERT INTO research_runs(id, owner_id, device_id, query, status, plan_json, steps_json, context_json, created_at, completed_at, error_code, report_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (run.run_id, run.request.owner_id, run.request.device_id, run.request.query, run.status,
                 json_text(list(run.plan.steps)), json_text([self._research_step(item) for item in run.steps]),
                 json_text(dict(run.request.context)), iso(run.created_at), iso(run.completed_at), run.error_code,
                 self._research_report_json(run.report)),
            )

    def update_research_run(self, run: Any) -> None:
        with self.database.transaction() as db:
            db.execute(
                "UPDATE research_runs SET status = ?, plan_json = ?, steps_json = ?, context_json = ?, completed_at = ?, error_code = ?, report_json = ? WHERE id = ? AND owner_id = ?",
                (run.status, json_text(list(run.plan.steps)), json_text([self._research_step(item) for item in run.steps]),
                 json_text(dict(run.request.context)), iso(run.completed_at), run.error_code,
                 self._research_report_json(run.report), run.run_id, run.request.owner_id),
            )

    def insert_research_source(self, run_id: str, source: Any) -> None:
        with self.database.transaction() as db:
            db.execute(
                "INSERT OR IGNORE INTO research_sources(id, run_id, locator, title, source_type, retrieved_at, fingerprint, trust) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (source.source_id, run_id, source.locator, source.title, source.source_type, iso(source.retrieved_at), source.fingerprint, source.trust),
            )

    def insert_research_evidence(self, run_id: str, evidence: Any) -> None:
        with self.database.transaction() as db:
            db.execute(
                "INSERT OR IGNORE INTO research_evidence(id, run_id, source_id, excerpt, locator, fingerprint, untrusted_content) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (evidence.evidence_id, run_id, evidence.source_id, evidence.excerpt, evidence.locator, evidence.fingerprint, int(evidence.untrusted_content)),
            )

    def research_run(self, owner_id: str, run_id: str) -> dict[str, Any] | None:
        row = self.database.connection.execute("SELECT * FROM research_runs WHERE owner_id = ? AND id = ?", (owner_id, run_id)).fetchone()
        return dict(row) if row else None

    def research_runs(self, owner_id: str) -> list[dict[str, Any]]:
        rows = self.database.connection.execute("SELECT * FROM research_runs WHERE owner_id = ? ORDER BY created_at DESC", (owner_id,)).fetchall()
        return [dict(row) for row in rows]

    def research_sources(self, run_id: str) -> list[dict[str, Any]]:
        rows = self.database.connection.execute("SELECT * FROM research_sources WHERE run_id = ? ORDER BY retrieved_at, id", (run_id,)).fetchall()
        return [dict(row) for row in rows]

    def research_evidence(self, run_id: str) -> list[dict[str, Any]]:
        rows = self.database.connection.execute("SELECT * FROM research_evidence WHERE run_id = ? ORDER BY id", (run_id,)).fetchall()
        return [dict(row) for row in rows]

    def reconcile_research_runs(self) -> int:
        with self.database.transaction() as db:
            cursor = db.execute(
                "UPDATE research_runs SET status = 'failed', completed_at = ?, error_code = 'process_restarted' WHERE status IN ('queued', 'running', 'planning', 'searching', 'reading', 'synthesizing')",
                (iso(utc_now()),),
            )
            return int(cursor.rowcount)

    @staticmethod
    def _research_step(step: Any) -> dict[str, object]:
        return {"step_id": step.step_id, "title": step.title, "status": step.status, "detail": step.detail}

    @staticmethod
    def _research_report_json(report: Any) -> str | None:
        if report is None:
            return None
        return json.dumps({
            "title": report.title, "summary": report.summary,
            "findings": [{"finding_id": item.finding_id, "statement": item.statement, "evidence_ids": list(item.evidence_ids), "confidence": item.confidence} for item in report.findings],
            "citations": [{"citation_id": item.citation_id, "evidence_id": item.evidence_id, "label": item.label, "valid": item.valid} for item in report.citations],
            "limitations": list(report.limitations),
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    # Phase 07 bounded missions -----------------------------------------
    def insert_mission(self, mission: Any) -> None:
        with self.database.transaction() as db:
            db.execute(
                "INSERT INTO missions(id, owner_id, goal_id, request, title, status, plan_json, budget_json, current_step, tool_calls, worker_runs, external_actions, replan_count, blocked_reason, approval_id, result_json, created_at, updated_at, completed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                self._mission_values(mission),
            )

    def update_mission(self, mission: Any) -> None:
        with self.database.transaction() as db:
            values = self._mission_values(mission)
            db.execute(
                "UPDATE missions SET goal_id = ?, request = ?, title = ?, status = ?, plan_json = ?, budget_json = ?, current_step = ?, tool_calls = ?, worker_runs = ?, external_actions = ?, replan_count = ?, blocked_reason = ?, approval_id = ?, result_json = ?, updated_at = ?, completed_at = ? WHERE id = ? AND owner_id = ?",
                (values[2], values[3], values[4], values[5], values[6], values[7], values[8], values[9], values[10], values[11], values[12], values[13], values[14], values[15], values[17], values[18], values[0], values[1]),
            )

    def mission(self, owner_id: str, mission_id: str) -> dict[str, Any] | None:
        row = self.database.connection.execute("SELECT * FROM missions WHERE owner_id = ? AND id = ?", (owner_id, mission_id)).fetchone()
        return dict(row) if row else None

    def missions(self, owner_id: str) -> list[dict[str, Any]]:
        rows = self.database.connection.execute("SELECT * FROM missions WHERE owner_id = ? ORDER BY updated_at DESC, id", (owner_id,)).fetchall()
        return [dict(row) for row in rows]

    def insert_mission_checkpoint(self, checkpoint: Any) -> None:
        with self.database.transaction() as db:
            db.execute(
                "INSERT INTO mission_checkpoints(id, mission_id, title, status, evidence_json, created_at, completed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (checkpoint.checkpoint_id, checkpoint.mission_id, checkpoint.title, checkpoint.status, json_text(dict(checkpoint.evidence)), iso(checkpoint.created_at), iso(checkpoint.completed_at)),
            )

    def mission_checkpoints(self, mission_id: str) -> list[dict[str, Any]]:
        rows = self.database.connection.execute("SELECT * FROM mission_checkpoints WHERE mission_id = ? ORDER BY created_at, id", (mission_id,)).fetchall()
        return [dict(row) for row in rows]

    def insert_mission_evidence(self, evidence: Any) -> None:
        with self.database.transaction() as db:
            db.execute(
                "INSERT INTO mission_evidence(id, mission_id, kind, locator, details_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (evidence.evidence_id, evidence.mission_id, evidence.kind, evidence.locator, json_text(dict(evidence.details)), iso(evidence.created_at)),
            )

    def mission_evidence(self, mission_id: str) -> list[dict[str, Any]]:
        rows = self.database.connection.execute("SELECT * FROM mission_evidence WHERE mission_id = ? ORDER BY created_at, id", (mission_id,)).fetchall()
        return [dict(row) for row in rows]

    def reconcile_missions(self) -> int:
        with self.database.transaction() as db:
            cursor = db.execute(
                "UPDATE missions SET status = 'failed', result_json = ?, updated_at = ?, completed_at = ? WHERE status IN ('running', 'waiting', 'waiting_approval')",
                (json_text({"status": "failed", "summary": "Mission interrupted by process restart", "evidence_ids": [], "error_code": "process_restarted"}), iso(utc_now()), iso(utc_now())),
            )
            return int(cursor.rowcount)

    @staticmethod
    def _mission_values(mission: Any) -> tuple[object, ...]:
        plan = mission.plan
        plan_json = None if plan is None else json_text({
            "steps": [{"step_id": item.step_id, "title": item.title, "status": item.status, "dependencies": list(item.dependencies), "required_capability": item.required_capability, "risk_level": item.risk_level, "approval_required": item.approval_required, "expected_evidence": list(item.expected_evidence), "detail": item.detail} for item in plan.steps],
            "dependencies": [{"mission_id": item.mission_id, "required_status": item.required_status} for item in plan.dependencies],
            "risk_level": plan.risk_level, "expected_evidence": list(plan.expected_evidence), "completion_criteria": list(plan.completion_criteria),
        })
        budget = mission.budget
        budget_json = json_text({"max_steps": budget.max_steps, "max_duration": budget.max_duration, "max_tool_calls": budget.max_tool_calls, "max_worker_runs": budget.max_worker_runs, "max_replans": budget.max_replans, "max_external_actions": budget.max_external_actions})
        result = mission.result
        result_json = None if result is None else json_text({"status": result.status, "summary": result.summary, "evidence_ids": list(result.evidence_ids), "error_code": result.error_code})
        return (mission.mission_id, mission.owner_id, mission.goal_id, mission.request, mission.title, mission.status.value if hasattr(mission.status, "value") else mission.status, plan_json, budget_json, mission.current_step, mission.tool_calls, mission.worker_runs, mission.external_actions, mission.replan_count, mission.blocked_reason, mission.approval_id, result_json, iso(mission.created_at), iso(mission.updated_at), iso(mission.completed_at))

    # Phase 07 product-owned skill metadata -----------------------------
    def insert_skill(self, skill: Any) -> None:
        manifest = skill.manifest
        payload = self._skill_manifest_json(manifest)
        status = manifest.status.value if hasattr(manifest.status, "value") else str(manifest.status)
        with self.database.transaction() as db:
            db.execute(
                "INSERT INTO skills(id, name, description, category, status, current_version, manifest_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET name=excluded.name, description=excluded.description, category=excluded.category, status=excluded.status, current_version=excluded.current_version, manifest_json=excluded.manifest_json, updated_at=excluded.updated_at",
                (manifest.skill_id, manifest.name, manifest.description, manifest.category, status, manifest.version, payload, iso(utc_now()), iso(utc_now())),
            )

    def update_skill(self, skill: Any) -> None:
        self.insert_skill(skill)

    def update_skill_status(self, skill_id: str, status: str) -> None:
        with self.database.transaction() as db:
            db.execute("UPDATE skills SET status = ?, updated_at = ? WHERE id = ?", (status, iso(utc_now()), skill_id))

    def insert_skill_version(self, version: Any) -> None:
        manifest = version.manifest
        with self.database.transaction() as db:
            db.execute(
                "INSERT OR IGNORE INTO skill_versions(id, skill_id, version, manifest_json, source, change_reason, previous_version, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (version.version_id, version.skill_id, version.version, self._skill_manifest_json(manifest), version.source, version.change_reason, version.previous_version, iso(version.created_at)),
            )

    def skill(self, skill_id: str) -> dict[str, Any] | None:
        row = self.database.connection.execute("SELECT * FROM skills WHERE id = ?", (skill_id,)).fetchone()
        return dict(row) if row else None

    def skills(self) -> list[dict[str, Any]]:
        rows = self.database.connection.execute("SELECT * FROM skills ORDER BY id").fetchall()
        return [dict(row) for row in rows]

    def skill_versions(self, skill_id: str) -> list[dict[str, Any]]:
        rows = self.database.connection.execute("SELECT * FROM skill_versions WHERE skill_id = ? ORDER BY created_at, id", (skill_id,)).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _skill_manifest_json(manifest: Any) -> str:
        return json_text({
            "skill_id": manifest.skill_id, "name": manifest.name, "description": manifest.description,
            "version": manifest.version, "category": manifest.category, "inputs": list(manifest.inputs),
            "outputs": list(manifest.outputs), "required_capabilities": list(manifest.required_capabilities),
            "risk_level": manifest.risk_level, "autonomy_level": manifest.autonomy_level,
            "estimated_duration": manifest.estimated_duration, "workspace_scope": manifest.workspace_scope,
            "network_requirement": manifest.network_requirement, "owner": manifest.owner,
            "status": manifest.status.value if hasattr(manifest.status, "value") else str(manifest.status),
        })

    # Phase 07 bounded workspace intelligence ---------------------------
    def insert_workspace_project(self, project: Any) -> None:
        payload = asdict(project)
        for key in ("project_id", "owner_id", "repo_path", "project_type", "approved", "updated_at"):
            payload.pop(key, None)
        payload = json_text(payload)
        with self.database.transaction() as db:
            db.execute("INSERT INTO workspace_projects(id, owner_id, repo_path, project_type, approved, metadata_json, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(owner_id, repo_path) DO UPDATE SET id=excluded.id, project_type=excluded.project_type, approved=excluded.approved, metadata_json=excluded.metadata_json, updated_at=excluded.updated_at", (project.project_id, project.owner_id, project.repo_path, project.project_type, int(project.approved), payload, iso(project.updated_at or utc_now())))

    def update_workspace_project(self, project: Any) -> None:
        self.insert_workspace_project(project)

    def workspace_project(self, owner_id: str, repo_path: str) -> dict[str, Any] | None:
        row = self.database.connection.execute("SELECT * FROM workspace_projects WHERE owner_id = ? AND repo_path = ?", (owner_id, repo_path)).fetchone()
        return dict(row) if row else None

    def workspace_project_by_id(self, owner_id: str, project_id: str) -> dict[str, Any] | None:
        row = self.database.connection.execute("SELECT * FROM workspace_projects WHERE owner_id = ? AND id = ?", (owner_id, project_id)).fetchone()
        return dict(row) if row else None

    def workspace_projects(self, owner_id: str) -> list[dict[str, Any]]:
        rows = self.database.connection.execute("SELECT * FROM workspace_projects WHERE owner_id = ? ORDER BY updated_at DESC, id", (owner_id,)).fetchall()
        return [dict(row) for row in rows]

    # Phase 07 intelligence, briefings, automation, evaluation ------------
    def insert_intelligence_finding(self, finding: Any) -> None:
        with self.database.transaction() as db:
            db.execute("INSERT OR REPLACE INTO intelligence_findings(id, owner_id, finding_type, severity, evidence_json, baseline_json, current_value_json, confidence, detected_at, affected_resource, recommended_action, auto_action_allowed, cooldown_seconds, status, fingerprint, resolved_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (finding.finding_id, finding.owner_id, finding.finding_type, finding.severity, json_text(dict(finding.evidence)), json_text(dict(finding.baseline)), json_text(finding.current_value), finding.confidence, iso(finding.detected_at), finding.affected_resource, finding.recommended_action, int(finding.auto_action_allowed), finding.cooldown_seconds, finding.status, finding.fingerprint, iso(finding.resolved_at)))

    def intelligence_finding(self, owner_id: str, finding_id: str) -> dict[str, Any] | None:
        row = self.database.connection.execute("SELECT * FROM intelligence_findings WHERE owner_id = ? AND id = ?", (owner_id, finding_id)).fetchone()
        return dict(row) if row else None

    def intelligence_findings(self, owner_id: str, active_only: bool = False) -> list[dict[str, Any]]:
        condition = " AND status = 'active'" if active_only else ""
        rows = self.database.connection.execute(f"SELECT * FROM intelligence_findings WHERE owner_id = ?{condition} ORDER BY detected_at DESC", (owner_id,)).fetchall()
        return [dict(row) for row in rows]

    def update_intelligence_finding(self, owner_id: str, finding_id: str, status: str, resolved_at: datetime | None = None) -> None:
        with self.database.transaction() as db:
            db.execute("UPDATE intelligence_findings SET status = ?, resolved_at = ? WHERE owner_id = ? AND id = ?", (status, iso(resolved_at), owner_id, finding_id))

    def insert_briefing(self, briefing: Any) -> None:
        with self.database.transaction() as db:
            db.execute("INSERT OR REPLACE INTO briefings(id, owner_id, briefing_type, title, summary, items_json, evidence_ids_json, created_at, delivered_at, dismissed_at, dedup_key) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (briefing.briefing_id, briefing.owner_id, briefing.briefing_type, briefing.title, briefing.summary, json_text(list(briefing.items)), json_text(list(briefing.evidence_ids)), iso(briefing.created_at), iso(briefing.delivered_at), iso(briefing.dismissed_at), briefing.dedup_key))

    def briefings(self, owner_id: str, briefing_type: str | None = None) -> list[dict[str, Any]]:
        if briefing_type:
            rows = self.database.connection.execute("SELECT * FROM briefings WHERE owner_id = ? AND briefing_type = ? ORDER BY created_at DESC", (owner_id, briefing_type)).fetchall()
        else:
            rows = self.database.connection.execute("SELECT * FROM briefings WHERE owner_id = ? ORDER BY created_at DESC", (owner_id,)).fetchall()
        return [dict(row) for row in rows]

    def insert_automation_rule(self, rule: Any) -> None:
        with self.database.transaction() as db:
            db.execute("INSERT OR REPLACE INTO automation_rules(id, owner_id, name, enabled, trigger_json, conditions_json, actions_json, risk_level, cooldown_seconds, last_run_at, next_run_at, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (rule.rule_id, rule.owner_id, rule.name, int(rule.enabled), json_text(asdict(rule.trigger)), json_text([asdict(item) for item in rule.conditions]), json_text([asdict(item) for item in rule.actions]), rule.risk_level, rule.cooldown_seconds, iso(rule.last_run_at), iso(rule.next_run_at), iso(rule.created_at), iso(rule.updated_at)))

    def automation_rules(self, owner_id: str) -> list[dict[str, Any]]:
        rows = self.database.connection.execute("SELECT * FROM automation_rules WHERE owner_id = ? ORDER BY created_at, id", (owner_id,)).fetchall()
        return [dict(row) for row in rows]

    def automation_rule(self, owner_id: str, rule_id: str) -> dict[str, Any] | None:
        row = self.database.connection.execute("SELECT * FROM automation_rules WHERE owner_id = ? AND id = ?", (owner_id, rule_id)).fetchone()
        return dict(row) if row else None

    def insert_automation_run(self, run: Any) -> None:
        with self.database.transaction() as db:
            db.execute("INSERT OR REPLACE INTO automation_runs(id, rule_id, status, trigger_event_id, result_json, started_at, completed_at) VALUES (?, ?, ?, ?, ?, ?, ?)", (run.run_id, run.rule_id, run.status, run.trigger_event_id, json_text(dict(run.result)), iso(run.started_at), iso(run.completed_at)))

    def automation_runs(self, rule_id: str) -> list[dict[str, Any]]:
        rows = self.database.connection.execute("SELECT * FROM automation_runs WHERE rule_id = ? ORDER BY started_at DESC", (rule_id,)).fetchall()
        return [dict(row) for row in rows]

    def insert_evaluation_run(self, run: Any) -> None:
        with self.database.transaction() as db:
            db.execute("INSERT OR REPLACE INTO evaluation_runs(id, owner_id, suite, status, passed, regression, summary, results_json, started_at, completed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (run.run_id, run.owner_id, run.suite, run.status, int(run.passed), int(run.regression), run.summary, json_text([asdict(item) if hasattr(item, "__dataclass_fields__") else dict(item) for item in run.results]), iso(run.started_at), iso(run.completed_at)))

    def evaluation_runs(self, owner_id: str | None = None) -> list[dict[str, Any]]:
        if owner_id:
            rows = self.database.connection.execute("SELECT * FROM evaluation_runs WHERE owner_id = ? ORDER BY started_at DESC", (owner_id,)).fetchall()
        else:
            rows = self.database.connection.execute("SELECT * FROM evaluation_runs ORDER BY started_at DESC").fetchall()
        return [dict(row) for row in rows]

    def insert_worker_delegation(self, delegation: Any) -> None:
        with self.database.transaction() as db:
            db.execute("INSERT OR REPLACE INTO worker_delegations(id, owner_id, worker, reason, scope, task, result_json, started_at, completed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (delegation.delegation_id, delegation.owner_id, delegation.worker, delegation.reason, delegation.scope, delegation.task, json_text(dict(delegation.result)), iso(delegation.started_at), iso(delegation.completed_at)))

    def worker_delegations(self, owner_id: str) -> list[dict[str, Any]]:
        rows = self.database.connection.execute("SELECT * FROM worker_delegations WHERE owner_id = ? ORDER BY started_at DESC", (owner_id,)).fetchall()
        return [dict(row) for row in rows]

    def insert_communication_insight(self, insight: Any) -> None:
        with self.database.transaction() as db:
            db.execute("INSERT OR REPLACE INTO communication_insights(id, owner_id, thread_id, insight_json, created_at) VALUES (?, ?, ?, ?, ?)", (insight.insight_id, insight.owner_id, insight.thread_id, json_text(asdict(insight)), iso(datetime.now(UTC))))

    def communication_insight(self, owner_id: str, thread_id: str) -> dict[str, Any] | None:
        row = self.database.connection.execute("SELECT * FROM communication_insights WHERE owner_id = ? AND thread_id = ?", (owner_id, thread_id)).fetchone()
        return dict(row) if row else None

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

    # Phase 04 device fabric --------------------------------------------
    def upsert_device_fabric(self, device: Any) -> None:
        with self.database.transaction() as db:
            db.execute(
                "INSERT INTO device_fabric VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET name=excluded.name, role=excluded.role, transport=excluded.transport, status=excluded.status, capabilities_json=excluded.capabilities_json, trust_level=excluded.trust_level, last_seen=excluded.last_seen, room_id=excluded.room_id, metadata_json=excluded.metadata_json",
                (
                    device.device_id, device.owner_id, device.name, device.role, device.transport, device.status,
                    json_text(sorted(device.capabilities)), device.trust_level, iso(device.last_seen), device.room_id,
                    json_text(dict(device.metadata)),
                ),
            )

    def fabric_device(self, owner_id: str, device_id: str) -> dict[str, Any] | None:
        row = self.database.connection.execute("SELECT * FROM device_fabric WHERE owner_id = ? AND id = ?", (owner_id, device_id)).fetchone()
        return dict(row) if row else None

    def fabric_devices(self, owner_id: str) -> list[dict[str, Any]]:
        rows = self.database.connection.execute("SELECT * FROM device_fabric WHERE owner_id = ? ORDER BY name, id", (owner_id,)).fetchall()
        return [dict(row) for row in rows]

    def update_device_fabric(self, owner_id: str, device_id: str, **fields: object) -> dict[str, Any]:
        allowed = {"name", "role", "transport", "status", "capabilities_json", "trust_level", "last_seen", "room_id", "metadata_json"}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"unsupported device fields: {sorted(unknown)}")
        assignments = ", ".join(f"{key} = ?" for key in fields)
        values = [iso(value) if isinstance(value, datetime) else value for value in fields.values()]
        with self.database.transaction() as db:
            db.execute(f"UPDATE device_fabric SET {assignments} WHERE owner_id = ? AND id = ?", (*values, owner_id, device_id))
        result = self.fabric_device(owner_id, device_id)
        if result is None:
            raise KeyError(device_id)
        return result
