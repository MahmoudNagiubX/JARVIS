from __future__ import annotations

import asyncio
import json
import threading
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from jarvis.automation import AutomationAction, AutomationExecutionBinding, AutomationRule, AutomationTrigger
from jarvis.api.core import CoreApplication
from jarvis.api.auth import StreamTicketService
from jarvis.api.http import CoreHttpServer
from jarvis.authority.identity.service import EnrollmentGrant
from jarvis.bootstrap import create_runtime
from jarvis.capabilities.registry import CapabilityRegistry
from jarvis.config import JarvisConfig
from jarvis.contracts import ApprovalRequest, LLMResponse
from jarvis.skills import Skill
from jarvis.events import Event, EventCategory, EventState
from jarvis.memory import CompositeMemoryExtractor, DeterministicMemoryExtractor, LocalModelMemoryExtractor
from jarvis.memory.service import DurableMemoryService
from jarvis.models.gateway import ModelGateway
from jarvis.models.providers import MockModelProvider
from jarvis.missions.service import MissionService
from jarvis.skills import SkillManifest, SkillStatus, SkillStep


class MasterAuditRemediationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:"))
        await self.runtime.start()
        self.identity = await self.runtime.identity.bootstrap_owner("Audit Owner")
        enrollment = await self.runtime.identity.create_enrollment(EnrollmentGrant(
            self.identity.owner_id, "Audit Device", "desktop", "windows", ("tool.request",),
            ("project.tests.run", "workspace.read"),
        ))
        issued = await self.runtime.identity.redeem_enrollment(enrollment.code)
        self.credential = issued.raw
        self.device = await self.runtime.identity.authenticate(issued.raw, issued.device_id)
        assert self.device is not None

    async def asyncTearDown(self) -> None:
        await self.runtime.shutdown()

    async def test_skill_execution_is_durable_and_exact_resume_is_idempotent(self) -> None:
        skill = Skill(
            SkillManifest("audit_consequential", "Audit consequential", "Test approval propagation."),
            (SkillStep("step-1", "Health", "system.health", risk_level="consequential", requires_approval=True),),
        )
        self.runtime.skills.register(skill)
        pending = await self.runtime.skill_executor.execute(skill.manifest.skill_id, {}, self.identity, self.device)
        self.assertEqual(pending.status, "waiting_approval")
        self.assertIsNotNone(pending.execution_id)
        row = self.runtime.repository.skill_execution(pending.execution_id or "")
        self.assertEqual(row["current_step"], 0)
        self.assertEqual(row["approval_id"], pending.approval_id)
        await self.runtime.approval.decide(pending.approval_id or "", True, self.identity.identity_id)
        completed = await self.runtime.skill_executor.resume(pending.execution_id or "", self.identity, self.device)
        duplicate = await self.runtime.skill_executor.resume(pending.execution_id or "", self.identity, self.device)
        self.assertEqual(completed.status, "completed")
        self.assertEqual(duplicate, completed)
        self.assertEqual(self.runtime.repository.skill_execution(pending.execution_id or "")["status"], "completed")

    async def test_skill_unknown_risk_and_learning_cannot_reduce_source_risk(self) -> None:
        unknown = Skill(SkillManifest("unknown_risk", "Unknown", "Unknown risk", risk_level="mystery"), (SkillStep("s", "Unknown", "system.health", risk_level="read"),))
        self.runtime.skills.register(unknown)
        denied = await self.runtime.skill_executor.execute("unknown_risk", {}, self.identity, self.device)
        self.assertEqual(denied.status, "denied")
        self.assertEqual(denied.error_code, "unknown_risk_level")
        from jarvis.skills import SkillLearningService

        draft = SkillLearningService().propose("Send report", ("communication.send",))
        approved = SkillLearningService().approve(draft)
        self.assertEqual(approved.manifest.risk_level, "consequential")
        self.assertTrue(approved.steps[0].requires_approval)

    async def test_mission_boolean_cannot_bypass_durable_approval(self) -> None:
        mission = await self.runtime.missions.create(__import__("jarvis.contracts", fromlist=["Mission"]).Mission("", self.identity.owner_id, "fix the failed build", "Fix build"))
        mission = await self.runtime.missions.plan(self.identity.owner_id, mission.mission_id)
        mission = await self.runtime.missions.start(self.identity.owner_id, mission.mission_id, self.identity, self.device)
        await self.runtime.missions.complete_step(self.identity.owner_id, mission.mission_id)
        await self.runtime.missions.advance(self.identity.owner_id, mission.mission_id)
        await self.runtime.missions.complete_step(self.identity.owner_id, mission.mission_id)
        waiting = await self.runtime.missions.advance(self.identity.owner_id, mission.mission_id)
        self.assertEqual(waiting.status.value, "waiting_approval")
        still_waiting = await self.runtime.missions.resume(self.identity.owner_id, mission.mission_id, approval_granted=True)
        self.assertEqual(still_waiting.status.value, "waiting_approval")
        await self.runtime.approval.decide(waiting.approval_id or "", True, self.identity.identity_id)
        resumed = await self.runtime.missions.resume(self.identity.owner_id, mission.mission_id, approval_granted=False)
        self.assertEqual(resumed.status.value, "running")

    async def test_mission_without_approval_engine_fails_closed(self) -> None:
        missions = MissionService(self.runtime.repository, self.runtime.event_bus, permission=self.runtime.missions.permission, approvals=None)
        mission_type = __import__("jarvis.contracts", fromlist=["Mission"]).Mission
        mission = await missions.create(mission_type("", self.identity.owner_id, "fix the failed build", "Fix build"))
        mission = await missions.plan(self.identity.owner_id, mission.mission_id)
        mission = await missions.start(self.identity.owner_id, mission.mission_id, self.identity, self.device)
        for _ in range(len(mission.plan.steps) + 1):
            mission = await missions.advance(self.identity.owner_id, mission.mission_id)
            if mission.status.value == "failed":
                break
            mission = await missions.complete_step(self.identity.owner_id, mission.mission_id)
        self.assertEqual(mission.status.value, "failed")
        self.assertEqual(mission.blocked_reason, "approval_engine_unavailable")
        self.assertIsNone(mission.approval_id)
        with self.assertRaises(ValueError):
            await missions.resume(self.identity.owner_id, mission.mission_id, approval_granted=True)

    async def test_automation_persists_binding_and_mission_child_reference(self) -> None:
        rule = await self.runtime.automation.create(AutomationRule(
            "", self.identity.owner_id, "Create bounded mission", AutomationTrigger("schedule", "*"),
            actions=(AutomationAction("mission", "Inspect status", {"request": "Inspect status"}),),
        ), self.identity, self.device)
        binding = self.runtime.repository.automation_binding(rule.rule_id, self.identity.owner_id)
        self.assertEqual(binding["device_id"], self.device.device_id)
        runs = await self.runtime.automation.run_schedule(self.identity.owner_id)
        self.assertEqual(runs[0].status, "completed")
        self.assertTrue(runs[0].child_ids)
        stored = self.runtime.repository.automation_runs(rule.rule_id)[0]
        self.assertIn(runs[0].child_ids[0], stored["result_json"])

    async def test_revoked_binding_is_not_used_by_scheduler(self) -> None:
        rule = await self.runtime.automation.create(AutomationRule(
            "", self.identity.owner_id, "Bound notification", AutomationTrigger("schedule", "*"),
            actions=(AutomationAction("notification", "Ready", {"message": "Ready"}),),
        ), self.identity, self.device)
        await self.runtime.identity.revoke_device(self.device.device_id)
        run = (await self.runtime.automation.run_schedule(self.identity.owner_id))[0]
        self.assertEqual(run.status, "failed")
        self.assertIn("automation_execution_binding_unavailable", str(run.result))

    async def test_automation_binding_is_a_privilege_ceiling(self) -> None:
        rule = await self.runtime.automation.create(AutomationRule(
            "", self.identity.owner_id, "Ceiling", AutomationTrigger("schedule", "*"),
            actions=(AutomationAction("notification", "Ready", {"message": "Ready"}),),
        ), self.identity, self.device)
        binding = self.runtime.repository.automation_binding(rule.rule_id, self.identity.owner_id)
        assert binding is not None
        with self.runtime.repository.database.transaction() as db:
            db.execute(
                "UPDATE devices SET capabilities_json = ?, scopes_json = ? WHERE id = ?",
                (json.dumps([*self.device.capabilities, "capability.new"]), json.dumps([*self.device.scopes, "scope.new"]), self.device.device_id),
            )
        principal = self.runtime.automation._resolve_binding(binding)
        self.assertIsNotNone(principal)
        self.assertNotIn("capability.new", principal[1].capabilities)
        self.assertNotIn("scope.new", principal[1].scopes)
        with self.runtime.repository.database.transaction() as db:
            db.execute("UPDATE devices SET capabilities_json = ?, scopes_json = ? WHERE id = ?", (json.dumps([]), json.dumps([]), self.device.device_id))
        constrained = self.runtime.automation._resolve_binding(binding)
        self.assertEqual(constrained[1].capabilities, frozenset())
        self.assertEqual(constrained[1].scopes, frozenset())
        await self.runtime.identity.revoke_device(self.device.device_id)
        self.assertIsNone(self.runtime.automation._resolve_binding(binding))
        run = (await self.runtime.automation.run_schedule(self.identity.owner_id))[0]
        self.assertEqual(run.status, "failed")

    async def test_offline_local_automations_continue_and_remote_skills_suppress(self) -> None:
        local_skill = Skill(
            SkillManifest("offline_local", "Offline local", "Runs locally.", required_capabilities=("workspace.read",)),
            (SkillStep("local", "Health", "system.health", required_capabilities=("workspace.read",)),),
        )
        remote_skill = Skill(
            SkillManifest("offline_remote", "Offline remote", "Requires remote access.", required_capabilities=("remote.lookup",), network_requirement="remote"),
            (SkillStep("remote", "Health", "system.health", required_capabilities=("remote.lookup",)),),
        )
        self.runtime.skills.register(local_skill)
        self.runtime.skills.register(remote_skill)
        local_actions = (
            AutomationAction("notification", "Offline notice", {"message": "local"}),
            AutomationAction("briefing", "morning"),
            AutomationAction("mission", "Inspect local state", {"request": "Inspect local state"}),
            AutomationAction("skill", local_skill.manifest.skill_id),
        )
        local_rules = []
        for index, action in enumerate(local_actions):
            local_rules.append(await self.runtime.automation.create(AutomationRule(
                "", self.identity.owner_id, f"Local offline {index}", AutomationTrigger("schedule", "*"), actions=(action,), cooldown_seconds=0,
            ), self.identity, self.device))
        remote_rule = await self.runtime.automation.create(AutomationRule(
            "", self.identity.owner_id, "Remote offline", AutomationTrigger("schedule", "*"),
            actions=(AutomationAction("skill", remote_skill.manifest.skill_id),), cooldown_seconds=0,
        ), self.identity, self.device)
        self.runtime.offline.set_online(False, "test")
        runs = {run.rule_id: run for run in await self.runtime.automation.run_schedule(self.identity.owner_id)}
        self.assertTrue(all(runs[rule.rule_id].status == "completed" for rule in local_rules), str({rule.rule_id: runs[rule.rule_id].result for rule in local_rules}))
        self.assertEqual(runs[remote_rule.rule_id].status, "failed")
        self.assertIn("automation_offline", str(runs[remote_rule.rule_id].result))

    async def test_local_memory_composite_falls_back_without_model_download(self) -> None:
        extractor = CompositeMemoryExtractor(local=None)
        candidates = await extractor.extract(self.identity.owner_id, "Keep your answers short.")
        self.assertEqual(candidates[0].structured_data["key"], "verbosity")
        self.assertEqual(DeterministicMemoryExtractor.extract_sync(self.identity.owner_id, "hello"), ())

    async def test_legacy_memory_extraction_delegates_to_the_deterministic_extractor(self) -> None:
        text = "Keep your answers short."
        self.assertEqual(
            DurableMemoryService.extract_candidates(self.identity.owner_id, text),
            DeterministicMemoryExtractor.extract_sync(self.identity.owner_id, text),
        )

    async def test_capability_truth_and_worker_exports_are_inspectable(self) -> None:
        from jarvis.agents.workers import WorkerCoordinator, WorkerStatus

        self.assertIsNotNone(WorkerCoordinator)
        self.assertIsNotNone(WorkerStatus)
        self.assertTrue(any(item["capability_id"] == "browser.read_page" for item in self.runtime.capabilities.consistency()))
        schemas = self.runtime.agent._tool_schemas()
        tests_schema = next(item for item in schemas if item["function"]["name"] == "project.tests.run")
        self.assertIn("project_path", tests_schema["function"]["parameters"]["required"])

    async def test_direct_skill_handler_is_denied_without_declared_capability(self) -> None:
        skill = Skill(
            SkillManifest("missing_capability", "Missing capability", "Must not run."),
            (SkillStep("step-1", "Health", "system.health", required_capabilities=("capability.never",)),),
        )
        self.runtime.skills.register(skill)
        result = await self.runtime.skill_executor.execute(skill.manifest.skill_id, {}, self.identity, self.device)
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error_code, "device_capability_missing")

    async def test_automation_skill_approval_is_exposed_and_linked(self) -> None:
        skill = Skill(
            SkillManifest("automation_consequential", "Automation consequential", "Approval fixture."),
            (SkillStep("step-1", "Health", "system.health", risk_level="consequential", requires_approval=True),),
        )
        self.runtime.skills.register(skill)
        rule = await self.runtime.automation.create(AutomationRule(
            "", self.identity.owner_id, "Run approval skill", AutomationTrigger("schedule", "*"),
            actions=(AutomationAction("skill", skill.manifest.skill_id),),
        ), self.identity, self.device)
        run = (await self.runtime.automation.run_schedule(self.identity.owner_id))[0]
        self.assertEqual(run.status, "awaiting_approval")
        self.assertEqual(len(run.child_ids), 2)
        self.assertEqual(run.binding_id, rule.binding_id)

    async def test_personalization_preferences_are_bounded_and_inspectable(self) -> None:
        await self.runtime.personalization.patch(self.identity.owner_id, {
            "preferred_tools": ["project.tests.run"], "common_project_directories": ["C:\\Jarivs"],
            "common_workflows": ["test then report"], "notification_dismissal_patterns": {"build": "dismissed"},
            "briefing_preference": "morning", "worker_preference": "local", "response_length": "short",
        })
        profile = await self.runtime.personalization.get(self.identity.owner_id)
        self.assertEqual(profile.values["preferred_tools"], ["project.tests.run"])
        self.assertEqual(profile.values["response_length"], "short")
        with self.assertRaises(ValueError):
            await self.runtime.personalization.update(self.identity.owner_id, __import__("jarvis.contracts", fromlist=["PersonalizationUpdate"]).PersonalizationUpdate("response_length", "x" * 3000))

    async def test_local_model_memory_extractor_requires_strict_json(self) -> None:
        def handler(request):
            return LLMResponse(request.request_id, '[{"content":"I prefer local tests.","category":"preference","confidence":0.9,"tags":["work"]}]', request.model, "stop", provider="mock")
        gateway = ModelGateway(JarvisConfig(environment="test"), providers={"mock": MockModelProvider(handler)})
        candidates = await LocalModelMemoryExtractor(gateway).extract(self.identity.owner_id, "remember local tests")
        self.assertEqual(candidates[0].category, "preference")

    async def test_stream_ticket_rejects_wrong_scope_and_expiry(self) -> None:
        tickets = StreamTicketService()
        principal = type("Principal", (), {"identity": self.identity, "device": self.device})()
        ticket = tickets.issue(principal, "events")
        self.assertIsNone(tickets.consume(ticket.token, "experience.events"))
        expired = replace(ticket, expires_at=datetime.now(UTC) - timedelta(seconds=1))
        tickets._tickets[expired.token] = expired
        self.assertIsNone(tickets.consume(expired.token, "events"))

    async def test_approval_and_events_are_owner_filtered(self) -> None:
        other_owner = self.runtime.repository.create_owner("Other")
        request = ApprovalRequest("approval-other", "test", other_owner, None, "test", datetime.now(UTC), datetime.now(UTC) + timedelta(minutes=1), {})
        await self.runtime.approval.request(request)
        application = CoreApplication(self.runtime)
        self.assertIsNone(await application.approval("approval-other", self.identity.owner_id))
        self.runtime.repository.append_event(Event.create("private.other", EventCategory.SYSTEM, actor_id=other_owner, payload={"owner_id": other_owner}, state=EventState.COMPLETED))
        self.assertFalse(any(row["event_type"] == "private.other" for row in application.events(owner_id=self.identity.owner_id)))

    async def test_automation_risk_is_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            await self.runtime.automation.create(AutomationRule("", self.identity.owner_id, "Critical", AutomationTrigger("schedule", "*"), risk_level="critical"))

    async def test_tool_schema_rejects_arguments_outside_registry_contract(self) -> None:
        spec = self.runtime.tools.get("status.read")
        self.assertIsNotNone(spec)
        with self.assertRaises(ValueError):
            spec.validate_arguments({"message": "unexpected"})

    async def test_private_gets_require_bearer_and_stream_tickets_are_one_use(self) -> None:
        server = CoreHttpServer(CoreApplication(self.runtime), port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://{server.address[0]}:{server.address[1]}"
        auth = {"credential": self.credential, "device_id": self.device.device_id, "identity_id": self.identity.identity_id}
        try:
            with self.assertRaises(HTTPError) as missing:
                urlopen(f"{base}/v1/memory?owner_id={self.identity.owner_id}")
            self.assertEqual(missing.exception.code, 401)
            with urlopen(Request(f"{base}/v1/memory?owner_id={self.identity.owner_id}", headers={"Authorization": f"Bearer {self.credential}", "X-JARVIS-Device-ID": self.device.device_id, "X-JARVIS-Identity-ID": self.identity.identity_id})) as response:
                self.assertEqual(response.status, 200)
            with self.assertRaises(HTTPError) as query_credential:
                urlopen(f"{base}/v1/memory?owner_id={self.identity.owner_id}&credential={self.credential}&device_id={self.device.device_id}&identity_id={self.identity.identity_id}")
            self.assertEqual(query_credential.exception.code, 401)
            ticket_request = Request(f"{base}/v1/auth/stream-ticket", data=json.dumps({**auth, "scope": "events"}).encode(), method="POST", headers={"Content-Type": "application/json"})
            with urlopen(ticket_request) as response:
                ticket = json.loads(response.read().decode())["stream_ticket"]
            with urlopen(f"{base}/v1/events/stream?stream_ticket={ticket}") as response:
                self.assertEqual(response.status, 200)
            with self.assertRaises(HTTPError) as reused:
                urlopen(f"{base}/v1/events/stream?stream_ticket={ticket}")
            self.assertEqual(reused.exception.code, 401)
        finally:
            server.shutdown()

    async def test_metadata_gets_require_auth_and_capabilities_are_device_bound(self) -> None:
        server = CoreHttpServer(CoreApplication(self.runtime), port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://{server.address[0]}:{server.address[1]}"
        headers = {"Authorization": f"Bearer {self.credential}", "X-JARVIS-Device-ID": self.device.device_id, "X-JARVIS-Identity-ID": self.identity.identity_id}
        routes = ("/v1/communications/channels", "/v1/capabilities?device_id=other-device", "/v1/engineering/providers", "/v1/perception/capabilities", "/v1/workers/developer/providers", "/v1/skills", "/v1/skills/run_tests", "/v1/skills/run_tests/versions")
        try:
            for route in routes:
                with self.assertRaises(HTTPError) as missing:
                    urlopen(f"{base}{route}")
                self.assertEqual(missing.exception.code, 401)
                with urlopen(Request(f"{base}{route}", headers=headers)) as response:
                    self.assertEqual(response.status, 200)
            with urlopen(f"{base}/v1/health") as response:
                self.assertEqual(response.status, 200)
            for route in ("/v1/hud", "/v1/experience/hud"):
                with urlopen(f"{base}{route}") as response:
                    self.assertEqual(response.status, 200)
        finally:
            server.shutdown()

    async def test_stream_ticket_rejects_a_revoked_bound_device(self) -> None:
        server = CoreHttpServer(CoreApplication(self.runtime), port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://{server.address[0]}:{server.address[1]}"
        body = {"credential": self.credential, "device_id": self.device.device_id, "identity_id": self.identity.identity_id, "scope": "events"}
        try:
            request = Request(f"{base}/v1/auth/stream-ticket", data=json.dumps(body).encode(), method="POST", headers={"Content-Type": "application/json"})
            with urlopen(request) as response:
                ticket = json.loads(response.read().decode())["stream_ticket"]
            await self.runtime.identity.revoke_device(self.device.device_id)
            with self.assertRaises(HTTPError) as revoked:
                urlopen(f"{base}/v1/events/stream?stream_ticket={ticket}")
            self.assertEqual(revoked.exception.code, 401)
        finally:
            server.shutdown()


if __name__ == "__main__":
    unittest.main()
