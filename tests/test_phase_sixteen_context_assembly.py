"""Phase 16: Personal Context Assembler and selection budget metadata tests."""

from __future__ import annotations

import json
import unittest

from jarvis.bootstrap import create_runtime
from jarvis.config import JarvisConfig
from jarvis.contracts import (
    DeviceIdentity,
    Goal,
    GoalStatus,
    Identity,
    MemoryCandidate,
)


class PhaseSixteenContextAssemblyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:"))
        await self.runtime.start()
        self.identity = await self.runtime.identity.bootstrap_owner("Local Owner")
        self.device = DeviceIdentity("device-1", self.identity.owner_id, "desktop", "windows", frozenset(), frozenset({"tool.request"}))
        self.assembler = self.runtime.context

    async def asyncTearDown(self) -> None:
        await self.runtime.shutdown()

    async def test_context_assembler_bounds_and_selection_metadata(self) -> None:
        owner_id = self.identity.owner_id

        # 1. Insert multiple memories (more than limit)
        for i in range(10):
            await self.runtime.memory.create(MemoryCandidate(owner_id, f"Project fact number {i} about Phoenix", "project"))

        # 2. Insert world state facts
        for i in range(15):
            await self.runtime.world_state.set_fact(owner_id, f"env.var_{i}", f"value_{i}", freshness_seconds=3600)

        # 3. Insert active goals
        for i in range(10):
            await self.runtime.goals.create(Goal(f"goal-{i}", owner_id, f"Complete milestone {i}", GoalStatus.ACTIVE, priority=i))

        # Assemble context for turn
        snapshot = await self.assembler.assemble(self.identity, self.device, "Phoenix")

        # Verify bounded caps
        self.assertLessEqual(len(snapshot.memories), 6)
        self.assertLessEqual(len(snapshot.world_state), 12)
        self.assertLessEqual(len(snapshot.goals), 8)

        # Verify selection metadata
        meta = snapshot.metadata
        self.assertIn("selected_memory_ids", meta)
        self.assertIn("selected_memory_count", meta)
        self.assertIn("memory_byte_estimate", meta)
        self.assertIn("selected_world_facts", meta)
        self.assertIn("active_goal_ids", meta)

        self.assertEqual(meta["selected_memory_count"], len(snapshot.memories))
        self.assertGreater(meta["memory_byte_estimate"], 0)

        # Verify prompt rendering is valid JSON and contains context
        prompt_text = self.assembler.prompt(snapshot)
        self.assertIn("JARVIS context", prompt_text)
        json_part = prompt_text.split(":\n", 1)[1]
        decoded = json.loads(json_part)
        self.assertIn("memories", decoded)
        self.assertIn("world_state", decoded)
        self.assertIn("goals", decoded)
        self.assertIn("metadata", decoded)
