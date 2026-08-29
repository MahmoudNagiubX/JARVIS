from __future__ import annotations

import asyncio
import json
import threading
import unittest
from datetime import UTC, datetime, timedelta
from urllib.request import Request, urlopen

from jarvis.autonomy.policy import AutonomyPolicy
from jarvis.api.core import CoreApplication
from jarvis.api.http import CoreHttpServer
from jarvis.bootstrap import create_runtime
from jarvis.config import JarvisConfig
from jarvis.contracts import (
    Goal,
    GoalStatus,
    MemoryCandidate,
    MemoryQuery,
    Observation,
    PersonalizationUpdate,
    WorldStateQuery,
)
from jarvis.offline.service import OfflineModeService
from jarvis.scheduler.service import BackgroundScheduler


class PhaseThreeIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:"))
        await self.runtime.start()
        self.identity = await self.runtime.identity.bootstrap_owner("Mahmoud")

    async def asyncTearDown(self) -> None:
        await self.runtime.shutdown()

    async def test_memory_is_useful_durable_searchable_and_user_editable(self) -> None:
        remembered = await self.runtime.memory.remember_from_conversation(self.identity.owner_id, "Keep your answers short.", "message-1")
        self.assertEqual(len(remembered), 1)
        duplicate = await self.runtime.memory.remember_from_conversation(self.identity.owner_id, "Keep your answers short.", "message-2")
        self.assertEqual(duplicate[0].memory_id, remembered[0].memory_id)
        self.assertEqual(len(await self.runtime.memory.search(MemoryQuery(self.identity.owner_id, "concise"))), 1)

        conflict = await self.runtime.memory.create(MemoryCandidate(self.identity.owner_id, "Mahmoud prefers detailed answers.", "preference", structured_data={"key": "verbosity", "value": "detailed"}, confidence=0.9))
        self.assertIsNotNone(conflict)
        self.assertEqual((await self.runtime.memory.get(self.identity.owner_id, remembered[0].memory_id)).status, "superseded")
        corrected = await self.runtime.memory.correct(self.identity.owner_id, conflict.memory_id, "Mahmoud prefers concise answers with details when requested.")
        self.assertIn("details", corrected.content)
        await self.runtime.memory.pin(self.identity.owner_id, corrected.memory_id)
        await self.runtime.memory.delete(self.identity.owner_id, corrected.memory_id)
        self.assertEqual(await self.runtime.memory.search(MemoryQuery(self.identity.owner_id, "details")), ())
        self.assertTrue(any(row["event_type"] == "memory.deleted" for row in self.runtime.repository.events()))

    async def test_world_state_fuses_sources_and_expires_without_becoming_memory(self) -> None:
        now = datetime.now(UTC)
        await self.runtime.world_state.observe(Observation("obs-1", "runtime", now, "build.status", {"value": "failed"}, 0.9, self.identity.owner_id, "build-1", 3600))
        await self.runtime.world_state.observe(Observation("obs-2", "system", now + timedelta(seconds=1), "build.status", {"value": "passed"}, 1.0, self.identity.owner_id, "build-2", 3600))
        facts = await self.runtime.world_state.facts(WorldStateQuery(self.identity.owner_id))
        build = next(fact for fact in facts if fact.key == "build.status")
        self.assertEqual(build.value, "failed")
        self.assertTrue(await self.runtime.world_state.conflicts(self.identity.owner_id))
        self.assertEqual(await self.runtime.memory.search(MemoryQuery(self.identity.owner_id, "build")), ())

        await self.runtime.world_state.set_fact(self.identity.owner_id, "temporary.status", "gone", expires_at=now - timedelta(seconds=1))
        self.assertGreaterEqual(await self.runtime.world_state.expire(self.identity.owner_id), 1)
        self.assertFalse(any(fact.key == "temporary.status" for fact in await self.runtime.world_state.facts(WorldStateQuery(self.identity.owner_id))))

    async def test_goals_are_bounded_persisted_state_machines(self) -> None:
        goal = await self.runtime.goals.create(Goal("goal-1", self.identity.owner_id, "Ship the Phase 03 foundation", GoalStatus.DRAFT, title="Ship Phase 03", priority=5, budget={"max_steps": 3, "max_replans": 1}, completion_criteria=("tests pass",)))
        goal = await self.runtime.goals.plan(self.identity.owner_id, goal.goal_id, ("Implement services", "Run tests"), "Run tests")
        self.assertEqual(len(goal.steps), 2)
        self.assertEqual((await self.runtime.goals.activate(self.identity.owner_id, goal.goal_id)).status, GoalStatus.ACTIVE)
        await self.runtime.goals.checkpoint(self.identity.owner_id, goal.goal_id, "Services implemented", completed=True, evidence={"tests": "pending"})
        self.assertEqual((await self.runtime.goals.pause(self.identity.owner_id, goal.goal_id)).status, GoalStatus.PAUSED)
        self.assertEqual((await self.runtime.goals.resume(self.identity.owner_id, goal.goal_id)).status, GoalStatus.ACTIVE)
        self.assertEqual((await self.runtime.goals.complete(self.identity.owner_id, goal.goal_id)).status, GoalStatus.COMPLETED)
        with self.assertRaises(ValueError):
            await self.runtime.goals.pause(self.identity.owner_id, goal.goal_id)

    async def test_proactive_detector_cooldown_and_safe_action(self) -> None:
        await self.runtime.world_state.set_fact(self.identity.owner_id, "build.status", "failed", source="build")
        await self.runtime.world_state.set_fact(self.identity.owner_id, "workspace.project_path", "C:\\Jarivs\\00_final\\jarvis", source="git")
        findings = await self.runtime.proactive.detect(self.identity.owner_id)
        build = next(finding for finding in findings if finding.finding_type == "build_failed")
        self.assertTrue(build.auto_action_allowed)
        self.assertEqual(await self.runtime.proactive.detect(self.identity.owner_id), ())
        await self.runtime.proactive.acknowledge(self.identity.owner_id, build.finding_id)

        enrollment = await self.runtime.identity.create_enrollment(__import__("jarvis.authority.identity.service", fromlist=["EnrollmentGrant"]).EnrollmentGrant(self.identity.owner_id, "Test Device", "desktop", "windows", ("tool.request",), ()))
        credential = await self.runtime.identity.redeem_enrollment(enrollment.code)
        device = await self.runtime.identity.authenticate(credential.raw, credential.device_id)
        self.assertIsNotNone(device)
        result = await self.runtime.proactive.execute_safe_action(self.identity.owner_id, build.finding_id, self.identity, device)
        self.assertEqual(result.status.value, "completed")

    async def test_personalization_offline_scheduler_and_context(self) -> None:
        profile = await self.runtime.personalization.update(self.identity.owner_id, PersonalizationUpdate("verbosity", "concise"))
        self.assertEqual(profile.values["preferred_name"], "Mahmoud")
        self.assertEqual(profile.values["verbosity"], "concise")
        await self.runtime.memory.remember_from_conversation(self.identity.owner_id, "I am working on the JARVIS project.")
        offline = OfflineModeService()
        offline.set_online(False, "test")
        self.assertFalse(offline.can_use("cloud.search").available)
        self.assertTrue(offline.can_use("local.memory").available)
        called: list[str] = []
        scheduler = BackgroundScheduler()
        job_id = scheduler.add("test", 1, lambda: called.append("ran"))
        await scheduler.run_once(job_id)
        self.assertEqual(called, ["ran"])
        snapshot = await self.runtime.context.assemble(self.identity, self._device(), "JARVIS project")
        self.assertTrue(snapshot.memories)
        self.assertIn("verbosity", snapshot.personalization)
        self.assertTrue(snapshot.tool_capabilities)

    async def test_phase_three_loopback_api_exposes_owned_resources(self) -> None:
        application = CoreApplication(self.runtime)
        principal = await application.ensure_demo_principal()
        server = CoreHttpServer(application, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://{server.address[0]}:{server.address[1]}"

        def request(method: str, path: str, payload: dict[str, object] | None = None, headers: dict[str, str] | None = None) -> tuple[int, dict[str, object]]:
            encoded = json.dumps(payload).encode("utf-8") if payload is not None else None
            request_object = Request(
                base + path,
                data=encoded,
                method=method,
                headers={"Content-Type": "application/json", **(headers or {})} if encoded else (headers or {}),
            )
            with urlopen(request_object) as response:
                body = response.read().decode("utf-8")
                return response.status, json.loads(body) if body else {}

        auth = {
            "credential": principal.credential,
            "device_id": principal.device.device_id,
            "identity_id": principal.identity.identity_id,
        }
        auth_headers = {"Authorization": f"Bearer {auth['credential']}", "X-JARVIS-Device-ID": auth["device_id"], "X-JARVIS-Identity-ID": auth["identity_id"]}
        try:
            status, created = request("POST", "/v1/memory", {**auth, "content": "Use local tests.", "category": "preference"})
            self.assertEqual(status, 201)
            self.assertEqual(created["category"], "preference")
            status, listed = request("GET", f"/v1/memory?owner_id={self.identity.owner_id}", headers=auth_headers)
            self.assertEqual(status, 200)
            self.assertTrue(listed["memories"])
            status, goal = request("POST", "/v1/goals", {**auth, "title": "API goal", "description": "Exercise the API"})
            self.assertEqual(status, 201)
            self.assertEqual(goal["status"], "draft")
            status, profile = request("GET", f"/v1/personalization/profile?owner_id={self.identity.owner_id}", headers=auth_headers)
            self.assertEqual(status, 200)
            self.assertEqual(profile["values"]["assistant_name"], "JARVIS")
        finally:
            server.shutdown()

    def _device(self):
        from jarvis.contracts import DeviceIdentity

        return DeviceIdentity("device-context", self.identity.owner_id, "desktop", "windows", frozenset(), frozenset())
