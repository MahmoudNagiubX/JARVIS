from __future__ import annotations

import unittest
from datetime import UTC, datetime

from jarvis.contracts import (
    ApprovalRequest,
    AuditRecord,
    ComputerAction,
    DeviceIdentity,
    Goal,
    Identity,
    LLMMessage,
    LLMRequest,
    LLMRole,
    MemoryRecord,
    Observation,
    PermissionDecision,
    PermissionEffect,
    ToolContext,
    ToolResult,
    ToolResultStatus,
    VoiceSessionState,
    WorldStateSnapshot,
)


class ContractTests(unittest.TestCase):
    def test_required_contracts_are_constructible_and_typed(self) -> None:
        now = datetime.now(UTC)
        identity = Identity("owner-1", "Owner", "owner-1", frozenset({"owner"}))
        device = DeviceIdentity(
            "device-1",
            "owner-1",
            "windows_client",
            "windows",
            frozenset({"computer.read"}),
            frozenset({"device.self.read"}),
            now,
        )
        self.assertEqual(identity.owner_id, device.owner_id)
        self.assertEqual(PermissionEffect.DENY, PermissionDecision(PermissionEffect.DENY, "test").effect)
        self.assertEqual(LLMRole.USER, LLMMessage(LLMRole.USER, "hello").role)
        self.assertEqual("req-1", LLMRequest("req-1", (LLMMessage(LLMRole.USER, "hello"),)).request_id)
        self.assertEqual(VoiceSessionState.IDLE.value, "idle")

        ToolContext(identity, device, "session-1", "corr-1")
        ToolResult(ToolResultStatus.SUCCEEDED, output={"ok": True}, verified=True)
        ComputerAction("observe", {"screen": 1})
        ApprovalRequest("approval-1", "computer.observe", "owner-1", "device-1", "test", now, now)
        AuditRecord("audit-1", "tool.completed", now, "owner-1", "device-1", "corr-1", "success")
        MemoryRecord("memory-1", "owner-1", "hello", now)
        Observation("observation-1", "test", now, "screen")
        Goal("goal-1", "owner-1", "test")
        WorldStateSnapshot("snapshot-1", now)
