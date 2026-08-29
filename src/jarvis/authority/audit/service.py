"""Append-only audit service backed by the runtime repository."""

from __future__ import annotations

from ...contracts import AuditRecord
from ...persistence.repositories import RuntimeRepository


class DurableAuditService:
    def __init__(self, repository: RuntimeRepository) -> None:
        self.repository = repository

    async def record(self, record: AuditRecord) -> None:
        self.repository.insert_audit(record)

    async def query(self, correlation_id: str | None = None) -> tuple[AuditRecord, ...]:
        rows = self.repository.audit(correlation_id)
        return tuple(
            AuditRecord(
                row["id"], row["event_type"], self._time(row["occurred_at"]), row["actor_id"],
                row["device_id"], row["correlation_id"], row["outcome"], row["reason_code"],
                self._json(row["metadata_json"]),
            )
            for row in rows
        )

    @staticmethod
    def _time(value: str):
        from datetime import datetime

        return datetime.fromisoformat(value)

    @staticmethod
    def _json(value: str) -> dict[str, object]:
        import json

        return json.loads(value)
