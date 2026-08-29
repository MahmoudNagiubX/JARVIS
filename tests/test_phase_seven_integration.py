from __future__ import annotations

import tempfile
import unittest
import json
import threading
from urllib.request import Request, urlopen
from pathlib import Path

from jarvis.automation import AutomationAction, AutomationCondition, AutomationRule, AutomationTrigger
from jarvis.bootstrap import create_runtime
from jarvis.briefings import BriefingService
from jarvis.config import JarvisConfig
from jarvis.contracts import DeviceIdentity
from jarvis.events import Event, EventCategory, EventState
from jarvis.evaluation import EvaluationCase, EvaluationService, RegressionSuite
from jarvis.skills import SkillLoader, SkillLearningService
from jarvis.agents.workers.coordination import WorkerCoordinator
from jarvis.agents.workers.runtime import LocalWorkerRuntime, WorkerCategory, WorkerResult, WorkerStatus
from jarvis.communications.intelligence import CommunicationIntelligenceService
from jarvis.contracts.communication import CommunicationMessage
from jarvis.api.core import CoreApplication
from jarvis.api.http import CoreHttpServer
from datetime import UTC, datetime


class PhaseSevenIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:"))
        await self.runtime.start()
        self.identity = await self.runtime.identity.bootstrap_owner("Phase Seven Owner")
        self.device = DeviceIdentity("phase-seven-device", self.identity.owner_id, "desktop", "windows", frozenset({"tool.request", "project.tests.run", "workspace.read"}), frozenset({"tool.request", "project.tests.run", "workspace.read"}))

    async def asyncTearDown(self) -> None:
        await self.runtime.shutdown()

    async def test_mission_budget_checkpoint_replan_and_approval_pause(self) -> None:
        mission = await self.runtime.missions.create(__import__("jarvis.contracts", fromlist=["Mission"]).Mission("", self.identity.owner_id, "fix the failed build", "Fix build"))
        mission = await self.runtime.missions.plan(self.identity.owner_id, mission.mission_id)
        mission = await self.runtime.missions.start(self.identity.owner_id, mission.mission_id, self.identity, self.device)
        await self.runtime.missions.complete_step(self.identity.owner_id, mission.mission_id, evidence={"tests": "observed"})
        await self.runtime.missions.advance(self.identity.owner_id, mission.mission_id)
        await self.runtime.missions.complete_step(self.identity.owner_id, mission.mission_id, evidence={"validation": "passed"})
        mission = await self.runtime.missions.advance(self.identity.owner_id, mission.mission_id)
        self.assertEqual(mission.status.value, "waiting_approval")
        approval = await self.runtime.approval.get(mission.approval_id or "")
        self.assertIsNotNone(approval)
        await self.runtime.approval.decide(mission.approval_id or "", True, self.identity.identity_id)
        mission = await self.runtime.missions.resume(self.identity.owner_id, mission.mission_id, approval_granted=True)
        self.assertEqual(mission.status.value, "running")
        with self.assertRaises(ValueError):
            await self.runtime.missions.record_tool_call(self.identity.owner_id, mission.mission_id, 21)
        checkpointed = await self.runtime.missions.checkpoint(self.identity.owner_id, mission.mission_id, "diagnostic checkpoint", completed=True, evidence={"source": "test"})
        self.assertEqual(len(checkpointed.checkpoints), 1)
        failed = await self.runtime.missions.fail(self.identity.owner_id, mission.mission_id, "validation_failed")
        replanned = await self.runtime.missions.replan(self.identity.owner_id, failed.mission_id, reason="validation evidence changed")
        self.assertEqual(replanned.replan_count, 1)
        self.assertTrue(replanned.plan and replanned.plan.steps)

    async def test_skills_progressive_loading_learning_and_permission_boundary(self) -> None:
        self.assertEqual(len(self.runtime.skills.list()), 8)
        skill = self.runtime.skills.get("system_health_check")
        self.assertIsNotNone(skill)
        output = await self.runtime.skill_executor.execute("system_health_check", {}, self.identity, self.device)
        self.assertEqual(output.status, "completed")
        disabled = self.runtime.skills.set_enabled("system_health_check", False)
        self.assertEqual(disabled.manifest.status.value, "disabled")
        self.assertEqual((await self.runtime.skill_executor.execute("system_health_check", {}, self.identity, self.device)).status, "unavailable")
        self.runtime.skills.set_enabled("system_health_check", True)
        draft = SkillLearningService().propose("review project", ("workspace.project_status", "summarize"))
        self.assertEqual(draft.skill.manifest.status.value, "draft")
        approved = SkillLearningService().approve(draft)
        self.assertEqual(approved.manifest.status.value, "active")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "SKILL.md"
            path.write_text("bounded instructions", encoding="utf-8")
            loaded = SkillLoader().load(__import__("jarvis.skills", fromlist=["Skill"]).Skill(skill.manifest, instructions_path=str(path)))
            self.assertEqual(loaded.instructions, "bounded instructions")

    async def test_workspace_findings_briefing_and_automation(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
            project = await self.runtime.workspace_intelligence.register(self.identity.owner_id, folder)
            self.assertEqual(project.project_type, "python")
            self.assertTrue(project.repo_map.configuration)
            for _ in range(3):
                event = Event.create("workspace.tests_failed", EventCategory.WORKSPACE, actor_id=self.identity.owner_id, payload={"owner_id": self.identity.owner_id, "project_id": project.project_id}, state=EventState.FAILED)
                self.runtime.repository.append_event(event)
            findings = await self.runtime.event_intelligence.detect(self.identity.owner_id)
            self.assertEqual(len(findings), 1)
            self.assertEqual(len(await self.runtime.event_intelligence.detect(self.identity.owner_id)), 0)
            briefing = await self.runtime.briefings.generate(self.identity.owner_id, "project")
            self.assertIsNotNone(briefing)
            self.assertTrue(briefing and briefing.evidence_ids)
            rule = await self.runtime.automation.create(AutomationRule("", self.identity.owner_id, "notify failures", AutomationTrigger("event", "workspace.tests_failed"), (AutomationCondition("project_id", "equals", project.project_id),), (AutomationAction("notification", "failure", {"message": "A bounded test failure was recorded"}))))
            event = Event.create("workspace.tests_failed", EventCategory.WORKSPACE, actor_id=self.identity.owner_id, payload={"owner_id": self.identity.owner_id, "project_id": project.project_id}, state=EventState.FAILED)
            await self.runtime.event_bus.publish(event)
            self.assertTrue(await self.runtime.automation.list(self.identity.owner_id))
            self.assertTrue(any(item["event_type"] == "notification.created" for item in self.runtime.repository.events()))
            self.assertTrue(rule.enabled)

    async def test_communications_workers_and_evaluation_are_bounded(self) -> None:
        communications = CommunicationIntelligenceService(self.runtime.repository, self.runtime.event_bus)
        message = CommunicationMessage("message-1", "local", "alice", "owner", "Urgent: please review the build by the deadline.", datetime.now(UTC), owner_id=self.identity.owner_id)
        insight = await communications.analyze(self.identity.owner_id, "thread-1", (message,))
        self.assertEqual(insight.priority, "high")
        self.assertTrue(insight.untrusted_input)
        self.assertFalse(communications.can_auto_send(self.identity.owner_id, "local", "alice")[0])

        async def handler(request):
            return WorkerResult("worker-test", WorkerStatus.SUCCEEDED, "read-only result", started_at=datetime.now(UTC), completed_at=datetime.now(UTC))
        coordinator = WorkerCoordinator(self.runtime.repository, self.runtime.event_bus, local=LocalWorkerRuntime({WorkerCategory.CODING: handler}), permission=self.runtime.permission)
        delegation = await coordinator.run(self.identity.owner_id, "inspect the code", workspace_scope=tempfile.gettempdir())
        self.assertEqual(delegation.result["status"], "succeeded")
        self.assertEqual(coordinator.select("browser research", required_capability="browser.read", internet_available=False).available, False)

        evaluations = EvaluationService(self.runtime.repository, self.runtime.event_bus)
        evaluations.register(RegressionSuite("phase-seven-fixture", (EvaluationCase("pass", "known pass", "determinism", lambda _: True), EvaluationCase("fail", "known fail", "determinism", lambda _: False, expected=True))))
        run = await evaluations.run("phase-seven-fixture", owner_id=self.identity.owner_id)
        self.assertFalse(run.passed)
        self.assertEqual(len(evaluations.list(self.identity.owner_id)), 1)

    async def test_phase_seven_loopback_api_exposes_owned_surfaces(self) -> None:
        enrollment = await self.runtime.identity.create_enrollment(__import__("jarvis.authority.identity.service", fromlist=["EnrollmentGrant"]).EnrollmentGrant(self.identity.owner_id, "Phase Seven HTTP", "desktop", "windows", ("tool.request",), ("workspace.read",)))
        issued = await self.runtime.identity.redeem_enrollment(enrollment.code)
        auth = {"credential": issued.raw, "device_id": issued.device_id, "identity_id": self.identity.identity_id}
        server = CoreHttpServer(CoreApplication(self.runtime), port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://{server.address[0]}:{server.address[1]}"
        try:
            with urlopen(f"{base}/v1/skills") as response:
                skills = json.loads(response.read().decode())
            self.assertEqual(len(skills["skills"]), 8)
            request = Request(f"{base}/v1/missions", data=json.dumps({**auth, "title": "API mission", "request": "inspect current status"}).encode(), headers={"Content-Type": "application/json"})
            with urlopen(request) as response:
                mission = json.loads(response.read().decode())
            self.assertEqual(mission["status"], "ready")
            with urlopen(f"{base}/v1/experience/state?owner_id={self.identity.owner_id}&credential={issued.raw}&device_id={issued.device_id}&identity_id={self.identity.identity_id}") as response:
                state = json.loads(response.read().decode())
            self.assertIn("missions", state)
            self.assertIn("skills", state)
        finally:
            server.shutdown()


if __name__ == "__main__":
    unittest.main()
