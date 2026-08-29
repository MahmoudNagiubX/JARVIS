"""In-memory and no-op implementations used only for foundation validation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from ..contracts import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalStatus,
    AuditRecord,
    BrowserAction,
    CommunicationMessage,
    ComputerAction,
    DeviceIdentity,
    Goal,
    GoalStatus,
    Identity,
    LLMRequest,
    LLMResponse,
    MemoryRecord,
    Observation,
    PermissionDecision,
    PermissionEffect,
    Tool,
    ToolContext,
    ToolResult,
    ToolResultStatus,
    VoiceSessionState,
    VoiceTranscript,
    WorldStateSnapshot,
)


class NoOpIdentityService:
    async def authenticate(self, credential: str, device_id: str) -> DeviceIdentity | None:
        del credential, device_id
        return None

    async def get_identity(self, identity_id: str) -> Identity | None:
        del identity_id
        return None


class FailClosedPermissionEngine:
    async def evaluate(
        self,
        identity: Identity | None,
        device: DeviceIdentity | None,
        action: str,
        resource: Mapping[str, object] | None = None,
    ) -> PermissionDecision:
        del identity, device, action, resource
        return PermissionDecision(PermissionEffect.DENY, "no_policy_configured")


class InMemoryApprovalEngine:
    def __init__(self) -> None:
        self._decisions: dict[str, ApprovalDecision] = {}

    async def request(self, request: ApprovalRequest) -> ApprovalDecision:
        decision = ApprovalDecision(
            approval_id=request.approval_id,
            status=ApprovalStatus.PENDING,
            decided_by=None,
            decided_at=None,
        )
        self._decisions[request.approval_id] = decision
        return decision

    async def decide(
        self, approval_id: str, approved: bool, decided_by: str
    ) -> ApprovalDecision:
        if approval_id not in self._decisions:
            raise KeyError(approval_id)
        decision = ApprovalDecision(
            approval_id=approval_id,
            status=ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED,
            decided_by=decided_by,
            decided_at=datetime.now(UTC),
        )
        self._decisions[approval_id] = decision
        return decision

    async def get(self, approval_id: str) -> ApprovalDecision | None:
        return self._decisions.get(approval_id)


class InMemoryAuditService:
    def __init__(self) -> None:
        self.records: list[AuditRecord] = []

    async def record(self, record: AuditRecord) -> None:
        self.records.append(record)

    async def query(self, correlation_id: str | None = None) -> tuple[AuditRecord, ...]:
        if correlation_id is None:
            return tuple(self.records)
        return tuple(record for record in self.records if record.correlation_id == correlation_id)


class NoOpLLMRouter:
    async def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            request_id=request.request_id,
            text="",
            model=None,
            finish_reason="not_configured",
        )


class EmptyToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[tuple[str, str], Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[(tool.name, tool.version)] = tool

    def get(self, name: str, version: str | None = None) -> Tool | None:
        if version is not None:
            return self._tools.get((name, version))
        matches = [tool for (tool_name, _), tool in self._tools.items() if tool_name == name]
        return matches[-1] if matches else None

    def list(self) -> tuple[Tool, ...]:
        return tuple(self._tools.values())


class InMemoryMemoryStore:
    def __init__(self) -> None:
        self.records: list[MemoryRecord] = []

    async def save(self, record: MemoryRecord) -> None:
        self.records.append(record)

    async def recall(self, owner_id: str, query: str, limit: int = 10) -> tuple[MemoryRecord, ...]:
        query_lower = query.casefold()
        matches = [
            record
            for record in reversed(self.records)
            if record.owner_id == owner_id and query_lower in record.content.casefold()
        ]
        return tuple(matches[:limit])


class InMemoryWorldState:
    def __init__(self) -> None:
        self.observations: list[Observation] = []

    async def observe(self, observation: Observation) -> None:
        self.observations.append(observation)

    async def snapshot(self) -> WorldStateSnapshot:
        return WorldStateSnapshot(
            snapshot_id="foundation-snapshot",
            created_at=datetime.now(UTC),
            observations=tuple(self.observations),
        )


class InMemoryGoalEngine:
    def __init__(self) -> None:
        self.goals: dict[str, Goal] = {}

    async def create(self, goal: Goal) -> Goal:
        self.goals[goal.goal_id] = goal
        return goal

    async def transition(self, goal_id: str, status: GoalStatus) -> Goal | None:
        goal = self.goals.get(goal_id)
        if goal is None:
            return None
        updated = replace(goal, status=status)
        self.goals[goal_id] = updated
        return updated


class NoOpComputerController:
    async def execute(self, action: ComputerAction, context: ToolContext) -> ToolResult:
        del action, context
        return ToolResult(ToolResultStatus.DENIED, error_code="computer_adapter_not_configured")


class NoOpBrowserController:
    async def execute(self, action: BrowserAction, context: ToolContext) -> ToolResult:
        del action, context
        return ToolResult(ToolResultStatus.DENIED, error_code="browser_adapter_not_configured")


class NoOpRealtimeVoiceSession:
    def __init__(self) -> None:
        self._state = VoiceSessionState.IDLE

    @property
    def state(self) -> VoiceSessionState:
        return self._state

    async def start(self) -> None:
        self._state = VoiceSessionState.LISTENING

    async def stop(self) -> None:
        self._state = VoiceSessionState.STOPPED


class NoOpSpeechToText:
    async def transcribe(self, audio: bytes) -> VoiceTranscript:
        del audio
        return VoiceTranscript(text="", is_final=True)


class NoOpTextToSpeech:
    async def synthesize(self, text: str) -> bytes:
        del text
        return b""


class NoOpCommunicationChannel:
    name = "unconfigured"

    async def send(self, message: CommunicationMessage) -> bool:
        del message
        return False
