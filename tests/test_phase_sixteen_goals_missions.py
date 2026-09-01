"""Phase 16: Durable Goals, Mission planning, budgets, checkpoints, and approval resume tests."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from jarvis.bootstrap import create_runtime
from jarvis.config import JarvisConfig
from jarvis.contracts import (
    ApprovalRequest,
    DeviceIdentity,
    Goal,
    GoalStatus,
    Mission,
    MissionBudget,
    MissionPlan,
    MissionStatus,
    MissionStep,
)


class PhaseSixteenGoalsMissionsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:"))
        await self.runtime.start()
        self.identity = await self.runtime.identity.bootstrap_owner("Local Owner")
        self.device = DeviceIdentity("device-1", self.identity.owner_id, "desktop", "windows", frozenset(), frozenset({"tool.request"}))
        self.goals = self.runtime.goals
        self.missions = self.runtime.missions

    async def asyncTearDown(self) -> None:
        await self.runtime.shutdown()

    async def test_goal_lifecycle_and_checkpoints(self) -> None:
        owner_id = self.identity.owner_id

        # 1. Create draft goal
        goal = await self.goals.create(
            Goal(
                goal_id="goal-test-1",
                owner_id=owner_id,
                statement="Ship Phase 16 Deliverable",
                status=GoalStatus.DRAFT,
                title="Ship Phase 16 Deliverable",
                description="Deliver personal intelligence and durable memory",
                priority=10,
            )
        )
        self.assertEqual(goal.status, GoalStatus.DRAFT)

        # 2. Activate goal
        active_goal = await self.goals.activate(owner_id, "goal-test-1")
        self.assertIsNotNone(active_goal)
        self.assertEqual(active_goal.status, GoalStatus.ACTIVE)

        # 3. Add checkpoint
        updated_goal = await self.goals.checkpoint(
            owner_id, "goal-test-1", "Memory Core Verified",
            evidence={"suite": "test_phase_sixteen_memory_core.py", "passed": True},
        )
        self.assertEqual(len(updated_goal.checkpoints), 1)
        cp_status = updated_goal.checkpoints[0]["status"] if isinstance(updated_goal.checkpoints[0], dict) else updated_goal.checkpoints[0].status
        self.assertEqual(cp_status, "open")

        # 4. Pause and Resume
        paused = await self.goals.pause(owner_id, "goal-test-1")
        self.assertEqual(paused.status, GoalStatus.PAUSED)

        resumed = await self.goals.resume(owner_id, "goal-test-1")
        self.assertEqual(resumed.status, GoalStatus.ACTIVE)

        # 5. Complete goal
        completed = await self.goals.complete(owner_id, "goal-test-1")
        self.assertEqual(completed.status, GoalStatus.COMPLETED)

    async def test_mission_lifecycle_and_budget_bounds(self) -> None:
        owner_id = self.identity.owner_id

        # Create mission with strict budget
        budget = MissionBudget(max_steps=3, max_tool_calls=2, max_duration=10.0)
        mission = await self.missions.create(
            Mission(
                mission_id="mission-1",
                owner_id=owner_id,
                request="Verify personal intelligence memory contracts",
                title="Audit memory system",
                status=MissionStatus.DRAFT,
                budget=budget,
            )
        )
        self.assertEqual(mission.status, MissionStatus.DRAFT)

        # Plan mission -> transitions to READY
        planned = await self.missions.plan(owner_id, "mission-1")
        self.assertEqual(planned.status, MissionStatus.READY)

        # Start mission
        started = await self.missions.start(owner_id, "mission-1", self.identity, self.device)
        self.assertEqual(started.status, MissionStatus.RUNNING)

        # Record tool calls within budget
        await self.missions.record_tool_call(owner_id, "mission-1", 1)
        await self.missions.record_tool_call(owner_id, "mission-1", 1)

        # Exceeding budget triggers failure
        with self.assertRaises(ValueError):
            await self.missions.record_tool_call(owner_id, "mission-1", 1)

    async def test_mission_approval_pause_and_exact_resume(self) -> None:
        owner_id = self.identity.owner_id

        plan = MissionPlan(
            steps=(
                MissionStep("step-1", "Safe inspect", "planned", (), "workspace.read_file", "read", False, (), "inspect codebase"),
                MissionStep("step-2", "Dangerous modify", "planned", ("step-1",), "workspace.write_file", "consequential", True, (), "apply changes"),
            ),
            dependencies=(),
            risk_level="consequential",
        )

        mission = await self.missions.create(
            Mission(
                mission_id="mission-appr-1",
                owner_id=owner_id,
                request="Edit project files with approval",
                title="Consequential edit mission",
                status=MissionStatus.DRAFT,
                plan=plan,
            )
        )
        await self.missions.plan(owner_id, "mission-appr-1")
        await self.missions.start(owner_id, "mission-appr-1", self.identity, self.device)

        # Advance to step 1 (safe)
        await self.missions.complete_step(owner_id, "mission-appr-1")
        # Advancing to step 2 (requires approval) pauses mission with WAITING_APPROVAL
        adv2 = await self.missions.advance(owner_id, "mission-appr-1")
        self.assertEqual(adv2.status, MissionStatus.WAITING_APPROVAL)
        self.assertIsNotNone(adv2.approval_id)

        # Resuming while approval is pending remains in WAITING_APPROVAL
        pending_resume = await self.missions.resume(owner_id, "mission-appr-1")
        self.assertEqual(pending_resume.status, MissionStatus.WAITING_APPROVAL)

        # Grant approval via approvals service
        await self.runtime.approval.decide(adv2.approval_id, True, owner_id)

        # Resuming with granted approval transitions to RUNNING
        resumed = await self.missions.resume(owner_id, "mission-appr-1")
        self.assertEqual(resumed.status, MissionStatus.RUNNING)

    async def test_startup_reconciliation_of_interrupted_missions(self) -> None:
        owner_id = self.identity.owner_id
        mission = await self.missions.create(
            Mission(
                mission_id="mission-interrupted",
                owner_id=owner_id,
                request="Run long task",
                title="Interrupted Mission",
                status=MissionStatus.DRAFT,
            )
        )
        await self.missions.plan(owner_id, "mission-interrupted")
        await self.missions.start(owner_id, "mission-interrupted", self.identity, self.device)

        # Reconcile missions
        reconciled_count = self.runtime.repository.reconcile_missions()
        self.assertGreaterEqual(reconciled_count, 1)

        row = self.runtime.repository.mission(owner_id, "mission-interrupted")
        self.assertEqual(row["status"], "failed")
        self.assertIn("process_restarted", str(row["result_json"]))
