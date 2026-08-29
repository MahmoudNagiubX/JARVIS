"""Small deterministic detectors; no opaque model score is treated as fact."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any, Iterable, Mapping
from uuid import uuid4

from ...bus import InMemoryEventBus
from ...events import Event, EventCategory, EventSeverity, EventState
from ...persistence.repositories import RuntimeRepository


@dataclass(frozen=True, slots=True)
class IntelligenceFinding:
    finding_id: str
    owner_id: str
    finding_type: str
    severity: str
    evidence: Mapping[str, object]
    baseline: Mapping[str, object]
    current_value: Mapping[str, object]
    confidence: float
    detected_at: datetime
    affected_resource: str
    recommended_action: str
    auto_action_allowed: bool = False
    cooldown_seconds: float = 900.0
    status: str = "active"
    fingerprint: str = ""
    resolved_at: datetime | None = None


class EventIntelligenceService:
    """Detect repeated operational signals from durable normalized events."""

    def __init__(self, repository: RuntimeRepository, event_bus: InMemoryEventBus, *, failure_threshold: int = 3, window_seconds: float = 3_600.0, cooldown_seconds: float = 900.0) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.failure_threshold = max(2, failure_threshold)
        self.window_seconds = max(60.0, window_seconds)
        self.cooldown_seconds = max(0.0, cooldown_seconds)

    async def detect(self, owner_id: str, events: Iterable[Mapping[str, object]] | None = None) -> tuple[IntelligenceFinding, ...]:
        now = datetime.now(UTC)
        rows = [self._event_row(item) for item in events] if events is not None else self.repository.events()
        failures: dict[str, list[Mapping[str, object]]] = {}
        for row in rows:
            if not self._belongs(row, owner_id):
                continue
            timestamp = self._time(row.get("timestamp"))
            if timestamp is None or now - timestamp > timedelta(seconds=self.window_seconds):
                continue
            event_type = str(row.get("event_type", ""))
            state = str(row.get("state", ""))
            severity = str(row.get("severity", ""))
            if state == EventState.FAILED.value or severity in {EventSeverity.ERROR.value, EventSeverity.CRITICAL.value} or event_type.endswith(("tests_failed", "build_failed")):
                key = self._failure_key(event_type, row)
                failures.setdefault(key, []).append(row)
        created: list[IntelligenceFinding] = []
        for key, values in failures.items():
            if len(values) < self.failure_threshold:
                continue
            finding_type = "repeated_test_failure" if "test" in key else "repeated_failure"
            fingerprint = sha256(f"{owner_id}:{finding_type}:{key}".encode()).hexdigest()[:32]
            if self._active_or_recent(owner_id, fingerprint, now):
                continue
            evidence = {"event_ids": [str(item.get("event_id")) for item in values[-10:]], "event_types": sorted({str(item.get("event_type")) for item in values})}
            finding = IntelligenceFinding(f"finding-{uuid4()}", owner_id, finding_type, "warning" if len(values) < self.failure_threshold * 2 else "error", evidence, {"window_seconds": self.window_seconds, "threshold": self.failure_threshold}, {"failure_count": len(values), "first_seen": str(values[0].get("timestamp")), "last_seen": str(values[-1].get("timestamp"))}, min(1.0, len(values) / (self.failure_threshold + 1)), now, key, "Inspect the latest failure evidence and run a bounded validation.", False, self.cooldown_seconds, "active", fingerprint)
            self.repository.insert_intelligence_finding(finding)
            await self._emit("intelligence.finding_created", finding, EventState.COMPLETED)
            created.append(finding)
        return tuple(created)

    async def resolve(self, owner_id: str, finding_id: str) -> IntelligenceFinding:
        row = self.repository.intelligence_finding(owner_id, finding_id)
        if row is None:
            raise KeyError(finding_id)
        now = datetime.now(UTC)
        self.repository.update_intelligence_finding(owner_id, finding_id, "resolved", now)
        finding = self._from_row(row, status="resolved", resolved_at=now)
        await self._emit("intelligence.finding_resolved", finding, EventState.COMPLETED)
        return finding

    async def list(self, owner_id: str, *, active_only: bool = False) -> tuple[IntelligenceFinding, ...]:
        return tuple(self._from_row(row) for row in self.repository.intelligence_findings(owner_id, active_only))

    def _active_or_recent(self, owner_id: str, fingerprint: str, now: datetime) -> bool:
        for row in self.repository.intelligence_findings(owner_id):
            if str(row.get("fingerprint")) != fingerprint:
                continue
            detected = self._time(row.get("detected_at"))
            if str(row.get("status")) == "active" or (detected and now - detected < timedelta(seconds=self.cooldown_seconds)):
                return True
        return False

    @staticmethod
    def _belongs(row: Mapping[str, object], owner_id: str) -> bool:
        payload = row.get("payload_json", {})
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {}
        return payload.get("owner_id") == owner_id or row.get("actor_id") == owner_id

    @staticmethod
    def _event_row(value: object) -> Mapping[str, object]:
        if isinstance(value, Event):
            return {"event_id": value.event_id, "event_type": value.event_type, "timestamp": value.timestamp.isoformat(), "correlation_id": value.correlation_id, "actor_id": value.actor_id, "payload_json": dict(value.payload), "severity": value.severity.value, "state": value.state.value}
        return value if isinstance(value, Mapping) else {}

    @staticmethod
    def _failure_key(event_type: str, row: Mapping[str, object]) -> str:
        payload = row.get("payload_json", {})
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {}
        resource = payload.get("project_id", payload.get("repo_path", payload.get("tool", "global")))
        return f"{event_type}:{resource}"

    async def _emit(self, event_type: str, finding: IntelligenceFinding, state: EventState) -> None:
        event = Event.create(event_type, EventCategory.INTELLIGENCE, correlation_id=f"finding-{finding.finding_id}", actor_id=finding.owner_id, payload={"owner_id": finding.owner_id, "finding_id": finding.finding_id, "finding_type": finding.finding_type, "severity": finding.severity, "affected_resource": finding.affected_resource, "evidence": dict(finding.evidence), "recommended_action": finding.recommended_action}, state=state, severity=EventSeverity.WARNING if finding.severity == "warning" else EventSeverity.ERROR if finding.severity == "error" else EventSeverity.INFO)
        self.repository.append_event(event)
        await self.event_bus.publish(event)

    @staticmethod
    def _time(value: object) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
        except ValueError:
            return None

    @staticmethod
    def _from_row(row: Mapping[str, object], *, status: str | None = None, resolved_at: datetime | None = None) -> IntelligenceFinding:
        def load(value: object) -> object:
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return {}
            return value
        detected = EventIntelligenceService._time(row.get("detected_at")) or datetime.now(UTC)
        return IntelligenceFinding(str(row["id"]), str(row["owner_id"]), str(row["finding_type"]), str(row["severity"]), load(row.get("evidence_json", {})), load(row.get("baseline_json", {})), load(row.get("current_value_json", {})), float(row.get("confidence", 0.0)), detected, str(row.get("affected_resource", "")), str(row.get("recommended_action", "")), bool(row.get("auto_action_allowed", 0)), float(row.get("cooldown_seconds", 0.0)), status or str(row.get("status", "active")), str(row.get("fingerprint", "")), resolved_at or EventIntelligenceService._time(row.get("resolved_at")))
