"""Phase 16: Complete offline operational verification tests."""

from __future__ import annotations

import unittest

from jarvis.bootstrap import create_runtime
from jarvis.config import JarvisConfig
from jarvis.contracts import (
    DeviceIdentity,
    Goal,
    GoalStatus,
    MemoryCandidate,
    MemoryQuery,
    Observation,
    WorldStateQuery,
)


class PhaseSixteenOfflineTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:"))
        await self.runtime.start()
        # Set offline state explicitly
        self.runtime.offline.set_online(False)
        self.identity = await self.runtime.identity.bootstrap_owner("Local Owner")
        self.device = DeviceIdentity("device-1", self.identity.owner_id, "desktop", "windows", frozenset(), frozenset({"tool.request"}))

    async def asyncTearDown(self) -> None:
        await self.runtime.shutdown()

    async def test_complete_local_personal_intelligence_stack_offline(self) -> None:
        owner_id = self.identity.owner_id

        # 1. Verify offline state
        self.assertFalse(self.runtime.offline.state.online)

        # 2. Durable Memory CRUD and recall works locally offline
        rec = await self.runtime.memory.create(
            MemoryCandidate(owner_id, "Local development uses SQLite and local models.", "fact")
        )
        self.assertIsNotNone(rec)
        results = await self.runtime.memory.recall(owner_id, "SQLite")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].memory_id, rec.memory_id)

        # 3. World state observations and facts work locally offline
        await self.runtime.world_state.set_fact(owner_id, "runtime.mode", "air_gapped", freshness_seconds=3600)
        facts = await self.runtime.world_state.facts(WorldStateQuery(owner_id))
        self.assertTrue(any(f.key == "runtime.mode" for f in facts))

        # 4. Goals and Missions work locally offline
        goal = await self.runtime.goals.create(
            Goal("goal-offline-1", owner_id, "Operate fully offline", GoalStatus.ACTIVE)
        )
        self.assertEqual(goal.status, GoalStatus.ACTIVE)

        # 5. Context assembly reflects offline state and local memory without remote lookups
        snapshot = await self.runtime.context.assemble(self.identity, self.device, "SQLite")
        self.assertFalse(snapshot.personalization.get("internet_online"))
        self.assertGreaterEqual(len(snapshot.memories), 1)
        self.assertGreaterEqual(len(snapshot.world_state), 1)
