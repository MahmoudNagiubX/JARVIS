"""Phase 16: World State freshness, TTL expiry, and strict memory firewall tests."""

from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from jarvis.bus import InMemoryEventBus
from jarvis.contracts import (
    Observation,
    WorldStateQuery,
)
from jarvis.memory.service import DurableMemoryService
from jarvis.persistence.db import SQLiteDatabase
from jarvis.persistence.repositories import RuntimeRepository
from jarvis.world_state.service import DurableWorldStateService


class PhaseSixteenWorldStateFirewallTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = str(Path(self.temp_dir.name) / "test.db")
        self.db = SQLiteDatabase(db_path)
        self.bus = InMemoryEventBus()
        self.repo = RuntimeRepository(self.db)
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO owners(id, display_name, status, created_at) "
                "VALUES ('owner-1', 'Local Owner', 'active', '2026-01-01T00:00:00+00:00')"
            )
        self.world_state = DurableWorldStateService(self.repo, self.bus)
        self.memory = DurableMemoryService(self.repo, self.bus)

    async def asyncTearDown(self) -> None:
        self.db.close()
        self.temp_dir.cleanup()

    async def test_freshness_ttl_and_expiry(self) -> None:
        now = datetime.now(UTC)
        past = now - timedelta(seconds=120)

        # Observation with 60 second freshness recorded 120 seconds ago (expired)
        obs_expired = Observation(
            observation_id="obs-expired",
            source="satellite",
            observed_at=past,
            subject="device.primary-pc.online",
            value={"value": True},
            confidence=0.9,
            owner_id="owner-1",
            freshness_seconds=60.0,
        )
        await self.world_state.observe(obs_expired)

        # Observation with fresh TTL
        obs_fresh = Observation(
            observation_id="obs-fresh",
            source="workspace",
            observed_at=now,
            subject="workspace.active_project",
            value={"value": "Project Phoenix"},
            confidence=0.95,
            owner_id="owner-1",
            freshness_seconds=3600.0,
        )
        await self.world_state.observe(obs_fresh)

        # 1. facts() with include_expired=False only returns fresh facts
        facts = await self.world_state.facts(WorldStateQuery("owner-1", include_expired=False))
        fact_keys = [f.key for f in facts]
        self.assertIn("workspace.active_project", fact_keys)
        self.assertNotIn("device.primary-pc.online", fact_keys)

        # 2. expire() marks expired facts in repository
        expired_count = await self.world_state.expire("owner-1")
        self.assertGreaterEqual(expired_count, 1)

    async def test_competing_observations_conflict_detection(self) -> None:
        now = datetime.now(UTC)

        # First observation: branch is feature/auth
        await self.world_state.set_fact("owner-1", "git.active_branch", "feature/auth", source="git", freshness_seconds=3600)

        # Competing observation from different source or value
        await self.world_state.set_fact("owner-1", "git.active_branch", "main", source="user", freshness_seconds=3600)

        # Check conflicts
        conflicts = await self.world_state.conflicts("owner-1")
        self.assertGreaterEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].key, "git.active_branch")

    async def test_strict_firewall_world_state_never_persists_to_memory(self) -> None:
        # Record observations in World State
        await self.world_state.set_fact("owner-1", "desktop.focused_window", "Code.exe", source="runtime", freshness_seconds=60)
        await self.world_state.set_fact("owner-1", "system.cpu_load", 42, source="venom", freshness_seconds=30)

        # Verify memories table remains completely empty (firewall)
        all_memories = self.repo.memories("owner-1", statuses=())
        self.assertEqual(len(all_memories), 0)

        # Verify memory search returns nothing
        recalled = await self.memory.recall("owner-1", "Code")
        self.assertEqual(len(recalled), 0)

    async def test_observation_owner_binding_cannot_split_persistence_and_facts(self) -> None:
        observation = Observation(
            "obs-owner-mismatch", "runtime", datetime.now(UTC), "desktop.focused", {"value": "Code"},
            owner_id="owner-2",
        )

        with self.assertRaisesRegex(ValueError, "world observation owner binding mismatch"):
            await self.world_state.observe(observation, owner_id="owner-1")

        self.assertEqual(self.repo.world_observations("owner-1"), [])
        self.assertEqual(self.repo.world_observations("owner-2"), [])

        unbound = Observation(
            "obs-owner-bound", "runtime", datetime.now(UTC), "desktop.focused", {"value": "Code"},
        )
        await self.world_state.observe(unbound, owner_id="owner-1")
        self.assertEqual(self.repo.world_observations("owner-1")[0]["owner_id"], "owner-1")
        facts = await self.world_state.facts(WorldStateQuery("owner-1"))
        self.assertTrue(any(fact.owner_id == "owner-1" for fact in facts))
