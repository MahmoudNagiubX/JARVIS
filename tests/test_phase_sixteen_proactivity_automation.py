"""Phase 16: Proactive Service detection, cooldown deduplication, and safe automation tests."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from jarvis.automation.service import (
    AutomationAction,
    AutomationCondition,
    AutomationRule,
    AutomationTrigger,
)
from jarvis.bootstrap import create_runtime
from jarvis.config import JarvisConfig
from jarvis.contracts import (
    DeviceIdentity,
    Goal,
    GoalStatus,
    Observation,
    ProactiveFinding,
)


class PhaseSixteenProactivityAutomationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:"))
        await self.runtime.start()
        self.identity = await self.runtime.identity.bootstrap_owner("Local Owner")
        self.device = DeviceIdentity("device-1", self.identity.owner_id, "desktop", "windows", frozenset(), frozenset({"tool.request"}))
        self.proactive = self.runtime.proactive
        self.automations = self.runtime.automation

    async def asyncTearDown(self) -> None:
        await self.runtime.shutdown()

    async def test_proactive_detection_and_cooldown_deduplication(self) -> None:
        owner_id = self.identity.owner_id

        # 1. Create a blocked goal
        await self.runtime.goals.create(
            Goal(
                goal_id="goal-blocked-1",
                owner_id=owner_id,
                statement="Deploy release to staging",
                status=GoalStatus.BLOCKED,
                title="Deploy release to staging",
                priority=10,
            )
        )

        # 2. Run detect
        findings = await self.proactive.detect(owner_id)
        self.assertGreaterEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(finding.finding_type, "goal_blocked")

        # 3. Running detect immediately again should suppress duplicate within cooldown
        findings_again = await self.proactive.detect(owner_id)
        self.assertEqual(len(findings_again), 0)

        # 4. Active list shows the recorded finding
        active = await self.proactive.list(owner_id, active_only=True)
        self.assertEqual(len(active), 1)

        # 5. Acknowledge finding
        acked = await self.proactive.acknowledge(owner_id, finding.finding_id)
        self.assertEqual(acked.status, "acknowledged")

        # After acknowledge, active_only list is empty
        active_after = await self.proactive.list(owner_id, active_only=True)
        self.assertEqual(len(active_after), 0)

    async def test_automation_rule_creation_and_execution(self) -> None:
        owner_id = self.identity.owner_id

        rule = AutomationRule(
            rule_id="auto-rule-1",
            owner_id=owner_id,
            name="Daily standup briefing",
            trigger=AutomationTrigger("event", "workspace.opened"),
            actions=(AutomationAction("briefing", "daily_standup"),),
            enabled=True,
        )
        created = await self.automations.create(rule)
        self.assertTrue(created.enabled)

        # List automations
        rules = await self.automations.list(owner_id)
        self.assertEqual(len(rules), 1)

        # Disable and Enable rule
        disabled = await self.automations.set_enabled(owner_id, "auto-rule-1", False)
        self.assertFalse(disabled.enabled)

        enabled = await self.automations.set_enabled(owner_id, "auto-rule-1", True)
        self.assertTrue(enabled.enabled)
