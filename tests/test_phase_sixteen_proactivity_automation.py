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

    async def test_proactive_finding_bridges_to_canonical_notification_and_experience_projection(self) -> None:
        """Newly detected proactive findings create canonical notifications projected to the HUD."""
        owner_id = self.identity.owner_id

        # 1. Create a blocked goal
        await self.runtime.goals.create(
            Goal(
                goal_id="goal-bridge-1",
                owner_id=owner_id,
                statement="Fix broken integration pipeline",
                status=GoalStatus.BLOCKED,
                title="Fix broken integration pipeline",
                priority=10,
            )
        )

        # 2. Run detect -> produces 1 finding and bridges to 1 Notification
        findings = await self.proactive.detect(owner_id)
        self.assertEqual(len(findings), 1)
        finding = findings[0]

        notifs = await self.runtime.notifications.list(owner_id, active_only=True)
        self.assertEqual(len(notifs), 1)
        notif = notifs[0]
        self.assertEqual(notif.source, "proactive")
        self.assertEqual(notif.severity, "warning")
        self.assertEqual(notif.metadata.get("finding_id"), finding.finding_id)
        self.assertEqual(notif.metadata.get("finding_type"), "goal_blocked")

        # 3. ExperienceProjection contains the proactive notification
        hud_state = await self.runtime.experience_projection.state(owner_id)
        hud_notifs = [n for n in hud_state.notifications if n.source == "proactive"]
        self.assertEqual(len(hud_notifs), 1)
        self.assertEqual(hud_notifs[0].notification_id, notif.notification_id)

        # 4. 100 repeated detect calls inside cooldown produce no duplicate findings and no duplicate notifications
        for _ in range(100):
            await self.proactive.detect(owner_id)

        all_findings = await self.proactive.list(owner_id)
        self.assertEqual(len(all_findings), 1)

        all_notifs = await self.runtime.notifications.list(owner_id, active_only=True)
        self.assertEqual(len(all_notifs), 1)

        # 5. Dismissing notification does NOT resolve the underlying durable finding
        await self.runtime.notifications.dismiss(owner_id, notif.notification_id)

        active_notifs_after_dismiss = await self.runtime.notifications.list(owner_id, active_only=True)
        self.assertEqual(len(active_notifs_after_dismiss), 0)

        finding_after_dismiss = await self.proactive.get(owner_id, finding.finding_id)
        self.assertIsNotNone(finding_after_dismiss)
        self.assertEqual(finding_after_dismiss.status, "detected")

    async def test_proactive_notification_restart_visibility(self) -> None:
        """Active durable findings survive process restart and remain visible in notifications."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "proactive_restart.db")
            cfg = JarvisConfig(environment="test", database_path=db_path)

            # Runtime 1
            rt1 = create_runtime(cfg)
            await rt1.start()
            try:
                owner = await rt1.identity.bootstrap_owner("Restart Owner")
                oid = owner.owner_id
                await rt1.goals.create(
                    Goal(goal_id="goal-restart-1", owner_id=oid, statement="Restart goal", status=GoalStatus.BLOCKED, title="Restart goal")
                )
                findings = await rt1.proactive.detect(oid)
                self.assertEqual(len(findings), 1)
                notifs = await rt1.notifications.list(oid, active_only=True)
                self.assertEqual(len(notifs), 1)
            finally:
                await rt1.shutdown()

            # Runtime 2 (fresh in-memory notification store, same SQLite database)
            rt2 = create_runtime(cfg)
            await rt2.start()
            try:
                # ExperienceProjection state queries rehydrate active durable findings
                hud = await rt2.experience_projection.state(oid)
                proactive_notifs = [n for n in hud.notifications if n.source == "proactive"]
                self.assertEqual(len(proactive_notifs), 1)
                self.assertIn("Goal Blocked", proactive_notifs[0].title)

                # Repeated projection calls do not create duplicate spam
                hud2 = await rt2.experience_projection.state(oid)
                proactive_notifs2 = [n for n in hud2.notifications if n.source == "proactive"]
                self.assertEqual(len(proactive_notifs2), 1)
            finally:
                await rt2.shutdown()
