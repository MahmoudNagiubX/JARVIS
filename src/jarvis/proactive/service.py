"""Evidence-based proactive detectors with cooldown and deduplication."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from ..authority.audit.service import DurableAuditService
from ..autonomy.policy import AutonomyPolicy
from ..bus import InMemoryEventBus
from ..contracts import (
    DeviceIdentity,
    FindingStatus,
    Identity,
    ProactiveFinding,
    ProactiveFindingType,
    ToolContext,
    WorldStateQuery,
)
from ..events import Event, EventCategory, EventState
from ..goals.engine import DurableGoalEngine
from ..persistence.repositories import RuntimeRepository
from ..tools.service import ToolExecutionService, ToolExecutionStatus
from ..world_state.service import DurableWorldStateService


class DurableProactiveService:
    """Rules are deterministic; an LLM is never asked to invent evidence."""

    def __init__(
        self,
        repository: RuntimeRepository,
        event_bus: InMemoryEventBus,
        world_state: DurableWorldStateService,
        goals: DurableGoalEngine,
        tools: ToolExecutionService,
        audit: DurableAuditService | None = None,
        autonomy: AutonomyPolicy | None = None,
    ) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.world_state = world_state
        self.goals = goals
        self.tools = tools
        self.audit = audit
        self.autonomy = autonomy or AutonomyPolicy()

    async def detect(self, owner_id: str, now: datetime | None = None) -> tuple[ProactiveFinding, ...]:
        observed_at = now or datetime.now(UTC)
        facts = await self.world_state.facts(WorldStateQuery(owner_id))
        by_key = {fact.key: fact for fact in facts}
        goals = await self.goals.list(owner_id)
        events = self.repository.events()
        candidates: list[tuple[str, str, dict[str, object], tuple[str, ...], str | None, bool, int]] = []

        build = self._status_fact(by_key, ("build.status", "build"))
        if build in {"failed", "failing", "error"}:
            fact = by_key.get("build.status")
            evidence = {"status": build, "fact": fact.fact_id if fact else None}
            candidates.append((ProactiveFindingType.BUILD_FAILED.value, "warning", evidence, self._event_ids(events, {"build.failed", "test.failed"}), "project.tests.run", True, 3600))

        test_failures = self._recent_events(events, {"test.failed", "tests.failed"}, observed_at - timedelta(hours=1))
        if len(test_failures) >= 3:
            candidates.append((ProactiveFindingType.TESTS_REPEATEDLY_FAILING.value, "warning", {"count": len(test_failures), "window": "1h"}, tuple(str(item["event_id"]) for item in test_failures), "project.tests.run", True, 3600))

        for goal in goals:
            if goal.status.value == "blocked":
                candidates.append((ProactiveFindingType.GOAL_BLOCKED.value, "warning", {"goal_id": goal.goal_id, "title": goal.title or goal.statement}, (), None, False, 3600))
            if goal.target_date and goal.status.value in {"active", "waiting", "proposed"} and observed_at <= goal.target_date <= observed_at + timedelta(hours=24):
                candidates.append((ProactiveFindingType.DEADLINE_APPROACHING.value, "warning", {"goal_id": goal.goal_id, "target_date": goal.target_date.isoformat()}, (), None, False, 3600))

        server_status = self._status_fact(by_key, ("dev_server.status", "development_server.status"))
        if server_status in {"stopped", "offline", "dead"}:
            candidates.append((ProactiveFindingType.DEV_SERVER_STOPPED.value, "warning", {"status": server_status}, (), None, False, 1800))
        task_status = self._status_fact(by_key, ("task.status",))
        if task_status in {"stalled", "idle_too_long"}:
            candidates.append((ProactiveFindingType.TASK_STALLED.value, "info", {"status": task_status}, (), None, False, 1800))
        disk = by_key.get("system.disk_free_gb")
        disk_value = self._number(disk.value) if disk else None
        if disk and disk_value is not None and disk_value < 5:
            candidates.append((ProactiveFindingType.DISK_SPACE_CRITICAL.value, "critical", {"free_gb": disk_value}, (disk.source_reference or disk.fact_id,), None, False, 1800))
        for event in self._recent_events(events, {"operation.completed", "device.disconnected"}, observed_at - timedelta(minutes=15)):
            finding_type = ProactiveFindingType.OPERATION_COMPLETED.value if event["event_type"] == "operation.completed" else ProactiveFindingType.DEVICE_DISCONNECTED.value
            candidates.append((finding_type, "info", dict(json.loads(event["payload_json"])), (str(event["event_id"]),), None, False, 900))
        for row in self.repository.pending_approvals(owner_id):
            created = datetime.fromisoformat(row["created_at"])
            if created <= observed_at - timedelta(minutes=10):
                candidates.append((ProactiveFindingType.APPROVAL_WAITING.value, "info", {"approval_id": row["id"]}, (), None, False, 1800))

        findings: list[ProactiveFinding] = []
        for item in candidates:
            finding = await self._record_candidate(owner_id, observed_at, *item)
            if finding is not None:
                findings.append(finding)
        return tuple(findings)

    async def list(self, owner_id: str, active_only: bool = False) -> tuple[ProactiveFinding, ...]:
        statuses = (FindingStatus.DETECTED.value,) if active_only else ()
        return tuple(self._finding(row) for row in self.repository.findings(owner_id, statuses))

    async def get(self, owner_id: str, finding_id: str) -> ProactiveFinding | None:
        row = self.repository.finding(owner_id, finding_id)
        return self._finding(row) if row else None

    async def acknowledge(self, owner_id: str, finding_id: str) -> ProactiveFinding:
        row = self.repository.update_finding(owner_id, finding_id, status=FindingStatus.ACKNOWLEDGED.value, acknowledged_at=datetime.now(UTC))
        await self._emit("proactive.notified", owner_id, {"finding_id": finding_id, "action": "acknowledged"}, EventState.COMPLETED)
        return self._finding(row)

    async def execute_safe_action(self, owner_id: str, finding_id: str, identity: Identity, device: DeviceIdentity) -> object:
        finding = await self.get(owner_id, finding_id)
        if finding is None:
            raise KeyError(finding_id)
        if not finding.recommended_action:
            raise ValueError("finding has no recommended action")
        decision = self.autonomy.decide(finding.recommended_action)
        if not finding.auto_action_allowed or not decision.allowed or decision.level.value > 2:
            raise ValueError("finding action is not allowed for automatic execution")
        await self._emit("proactive.auto_action_started", owner_id, {"finding_id": finding_id, "action": finding.recommended_action}, EventState.ACCEPTED)
        arguments = {key: value for key, value in finding.evidence.items() if key in {"project_path", "test_file"}}
        if "project_path" not in arguments:
            path_facts = await self.world_state.facts(WorldStateQuery(owner_id, "workspace.project_path"))
            if path_facts:
                arguments["project_path"] = path_facts[0].value
        context = ToolContext(identity, device, f"proactive-{finding_id}", f"proactive-{finding_id}")
        result = await self.tools.execute(finding.recommended_action, arguments, context)
        if result.status is ToolExecutionStatus.COMPLETED:
            self.repository.update_finding(owner_id, finding_id, status=FindingStatus.ACTIONED.value, last_notified_at=datetime.now(UTC))
            await self._emit("proactive.auto_action_completed", owner_id, {"finding_id": finding_id, "action": finding.recommended_action}, EventState.COMPLETED)
        return result

    async def _record_candidate(self, owner_id: str, now: datetime, finding_type: str, severity: str, evidence: dict[str, object], source_events: tuple[str, ...], action: str | None, auto: bool, cooldown: int) -> ProactiveFinding | None:
        fingerprint = hashlib.sha256(json.dumps(evidence, sort_keys=True, default=str).encode()).hexdigest()
        for row in self.repository.findings(owner_id):
            if row["finding_type"] != finding_type:
                continue
            age = now - datetime.fromisoformat(row["detected_at"])
            if age.total_seconds() < int(row["cooldown_seconds"]):
                old_fingerprint = hashlib.sha256(json.dumps(json.loads(row["evidence_json"]), sort_keys=True, default=str).encode()).hexdigest()
                await self._emit("proactive.suppressed", owner_id, {"finding_type": finding_type, "duplicate": old_fingerprint == fingerprint})
                return None
        decision = self.autonomy.decide(action) if action else None
        allowed = auto and decision is not None and decision.level.value <= 2 and decision.allowed
        finding = ProactiveFinding(f"finding-{uuid4()}", owner_id, finding_type, severity, evidence, source_events, now, action, allowed, cooldown)
        self.repository.insert_finding(finding)
        await self._emit("proactive.detected", owner_id, {"finding_id": finding.finding_id, "type": finding_type, "severity": severity, "evidence": evidence})
        return finding

    @staticmethod
    def _status_fact(facts: Mapping[str, object], keys: tuple[str, ...]) -> str | None:
        for key in keys:
            fact = facts.get(key)
            if fact is None:
                continue
            value = fact.value
            if isinstance(value, Mapping):
                value = value.get("status") or value.get("state")
            if isinstance(value, str):
                return value.casefold()
        return None

    @staticmethod
    def _number(value: object) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, Mapping):
            candidate = value.get("value") or value.get("free_gb")
            return float(candidate) if isinstance(candidate, (int, float)) else None
        return None

    @staticmethod
    def _recent_events(events: list[dict[str, object]], event_types: set[str], since: datetime) -> list[dict[str, object]]:
        return [event for event in events if event["event_type"] in event_types and datetime.fromisoformat(event["timestamp"]) >= since]

    @staticmethod
    def _event_ids(events: list[dict[str, object]], event_types: set[str]) -> tuple[str, ...]:
        return tuple(str(event["event_id"]) for event in events if event["event_type"] in event_types)[-20:]

    @staticmethod
    def _finding(row: Mapping[str, object]) -> ProactiveFinding:
        return ProactiveFinding(row["id"], row["owner_id"], row["finding_type"], row["severity"], json.loads(row["evidence_json"]), tuple(json.loads(row["source_events_json"])), datetime.fromisoformat(row["detected_at"]), row["recommended_action"], bool(row["auto_action_allowed"]), row["cooldown_seconds"], row["status"], datetime.fromisoformat(row["acknowledged_at"]) if row["acknowledged_at"] else None, datetime.fromisoformat(row["last_notified_at"]) if row["last_notified_at"] else None)

    async def _emit(self, event_type: str, owner_id: str, payload: dict[str, object], state: EventState = EventState.EMITTED) -> None:
        event = Event.create(event_type, EventCategory.PROACTIVE, correlation_id=f"proactive-{owner_id}", actor_id=owner_id, payload=payload, state=state)
        self.repository.append_event(event)
        await self.event_bus.publish(event)
