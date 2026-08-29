"""Fail-closed autonomy levels for automatic actions."""

from __future__ import annotations

from collections.abc import Sequence

from ..contracts import AutonomyDecision, AutonomyLevel, AutonomyRule


class AutonomyPolicy:
    def __init__(self, rules: Sequence[AutonomyRule] = ()) -> None:
        self.rules = tuple(rules) or (
            AutonomyRule("project.tests.run", AutonomyLevel.SAFE_AUTO, "bounded local test runner"),
            AutonomyRule("workspace.inspect", AutonomyLevel.SAFE_AUTO, "read-only workspace inspection"),
            AutonomyRule("computer.observe", AutonomyLevel.OBSERVE, "observation only"),
            AutonomyRule("computer.input", AutonomyLevel.APPROVAL_REQUIRED, "computer input changes state"),
            AutonomyRule("message.send", AutonomyLevel.APPROVAL_REQUIRED, "external communication requires approval"),
            AutonomyRule("files.delete", AutonomyLevel.BLOCKED, "destructive file operation"),
            AutonomyRule("account.", AutonomyLevel.BLOCKED, "account/security operation"),
        )

    def decide(self, action: str) -> AutonomyDecision:
        for rule in self.rules:
            if action == rule.action_prefix or action.startswith(rule.action_prefix + ".") or action.startswith(rule.action_prefix):
                return AutonomyDecision(
                    action,
                    rule.level,
                    rule.level in {AutonomyLevel.SAFE_AUTO, AutonomyLevel.AUTO_NOTIFY, AutonomyLevel.OBSERVE},
                    rule.level == AutonomyLevel.APPROVAL_REQUIRED,
                    rule.reason,
                )
        return AutonomyDecision(action, AutonomyLevel.APPROVAL_REQUIRED, False, True, "unknown action requires approval")
