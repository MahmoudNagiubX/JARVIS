"""Phase 16: Durable memory policy, extraction, conflict versioning, and retention tests."""

from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from jarvis.bus import InMemoryEventBus
from jarvis.contracts import (
    MemoryCandidate,
    MemoryQuery,
    MemorySensitivity,
)
from jarvis.memory.extractors import DeterministicMemoryExtractor
from jarvis.memory.policy import MemoryPolicy
from jarvis.memory.service import DurableMemoryService
from jarvis.persistence.db import SQLiteDatabase
from jarvis.persistence.repositories import RuntimeRepository


class PhaseSixteenMemoryCoreTests(unittest.IsolatedAsyncioTestCase):
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
        self.service = DurableMemoryService(self.repo, self.bus)

    async def asyncTearDown(self) -> None:
        self.db.close()
        self.temp_dir.cleanup()

    def test_memory_policy_blocks_credentials(self) -> None:
        policy = MemoryPolicy()

        # Blocked password / API key / token
        self.assertFalse(policy.evaluate(MemoryCandidate("owner-1", "My password is supersecret123", "fact")).allowed)
        self.assertFalse(policy.evaluate(MemoryCandidate("owner-1", "AWS_SECRET_ACCESS_KEY=abcd1234efgh5678", "fact")).allowed)
        self.assertFalse(policy.evaluate(MemoryCandidate("owner-1", "bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz", "fact")).allowed)
        self.assertFalse(policy.evaluate(MemoryCandidate("owner-1", "sk-12345678901234567890abcdef", "fact")).allowed)
        self.assertFalse(policy.evaluate(MemoryCandidate("owner-1", "session_token=xyz12345", "fact")).allowed)

        # Blocked secret sensitivity
        self.assertFalse(policy.evaluate(MemoryCandidate("owner-1", "Confidential trade secret", "fact", sensitivity=MemorySensitivity.SECRET.value)).allowed)

        # Blocked raw media
        self.assertFalse(policy.evaluate(MemoryCandidate("owner-1", "raw audio stream", "raw_audio")).allowed)
        self.assertFalse(policy.evaluate(MemoryCandidate("owner-1", "raw audio data", "fact", source="audio")).allowed)

        # Allowed valid memory
        decision = policy.evaluate(MemoryCandidate("owner-1", "Project Phoenix uses PostgreSQL.", "project"))
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.normalized_content, "Project Phoenix uses PostgreSQL.")

    def test_memory_policy_scans_structured_metadata_tags_and_source_reference(self) -> None:
        policy = MemoryPolicy()

        structured_secret = policy.evaluate(
            MemoryCandidate(
                "owner-1", "The project uses a provider.", "project",
                structured_data={"provider": "groq", "api_key": "not-for-storage"},
            )
        )
        source_secret = policy.evaluate(
            MemoryCandidate(
                "owner-1", "The project uses a provider.", "project",
                source_reference="research://run-1?password=not-for-storage",
            )
        )
        tag_secret = policy.evaluate(
            MemoryCandidate(
                "owner-1", "The project uses a provider.", "project",
                tags=("api_key",),
            )
        )

        self.assertFalse(structured_secret.allowed)
        self.assertFalse(source_secret.allowed)
        self.assertFalse(tag_secret.allowed)
        self.assertTrue(policy.evaluate(MemoryCandidate(
            "owner-1", "The project uses a provider.", "project",
            structured_data={"provider": "groq", "model": "reasoning"},
            source_reference="research-run-1",
            tags=("project",),
        )).allowed)

    def test_deterministic_memory_extractor(self) -> None:
        extractor = DeterministicMemoryExtractor()

        # Verbosity preference
        c = extractor.extract_sync("owner-1", "Please keep your answers short.")
        self.assertEqual(len(c), 1)
        self.assertEqual(c[0].category, "preference")
        self.assertEqual(c[0].structured_data.get("key"), "verbosity")

        # Name
        c = extractor.extract_sync("owner-1", "Call me Mahmoud.")
        self.assertEqual(len(c), 1)
        self.assertEqual(c[0].category, "profile")
        self.assertEqual(c[0].structured_data.get("value"), "Mahmoud")

        # Preferred editor
        c = extractor.extract_sync("owner-1", "My preferred editor is VS Code.")
        self.assertEqual(len(c), 1)
        self.assertEqual(c[0].category, "preference")
        self.assertEqual(c[0].structured_data.get("key"), "preferred_editor")
        self.assertEqual(c[0].structured_data.get("value"), "VS Code")

        # Project tech stack
        c = extractor.extract_sync("owner-1", "Project Phoenix uses PostgreSQL.")
        self.assertGreaterEqual(len(c), 1)
        tech_cand = [item for item in c if item.category == "project"][0]
        self.assertEqual(tech_cand.structured_data.get("project"), "Phoenix")
        self.assertIn("PostgreSQL", str(tech_cand.structured_data.get("technology")))

        # Goal
        c = extractor.extract_sync("owner-1", "My goal is to ship the Phase 16 personal intelligence deliverable.")
        self.assertGreaterEqual(len(c), 1)
        self.assertTrue(any(item.category == "goal" for item in c))

        # Deadline
        c = extractor.extract_sync("owner-1", "Deadline is Friday at 5 PM.")
        self.assertGreaterEqual(len(c), 1)
        self.assertTrue(any(item.category == "task" for item in c))

    async def test_memory_conflict_and_superseding(self) -> None:
        # 1. Store initial editor preference
        cand1 = MemoryCandidate(
            "owner-1", "Preferred editor is PyCharm.", "preference",
            structured_data={"key": "preferred_editor", "value": "PyCharm"},
        )
        rec1 = await self.service.create(cand1)
        self.assertIsNotNone(rec1)
        self.assertEqual(rec1.status, "active")
        self.assertIsNone(rec1.supersedes)

        # 2. Store updated editor preference (conflict detected by key)
        cand2 = MemoryCandidate(
            "owner-1", "Preferred editor is VS Code.", "preference",
            structured_data={"key": "preferred_editor", "value": "VS Code"},
        )
        rec2 = await self.service.create(cand2)
        self.assertIsNotNone(rec2)
        self.assertEqual(rec2.status, "active")
        self.assertEqual(rec2.supersedes, rec1.memory_id)

        # 3. Verify old record is marked superseded
        old_rec = await self.service.get("owner-1", rec1.memory_id)
        self.assertEqual(old_rec.status, "superseded")

        # 4. Search only returns active records by default
        active_recs = await self.service.search(MemoryQuery("owner-1", text="editor"))
        self.assertEqual(len(active_recs), 1)
        self.assertEqual(active_recs[0].memory_id, rec2.memory_id)
        self.assertIn("VS Code", active_recs[0].content)

    async def test_memory_delete_and_forget_category(self) -> None:
        rec = await self.service.create(MemoryCandidate("owner-1", "Remember to drink water.", "habit"))
        self.assertIsNotNone(rec)

        # Delete memory
        await self.service.delete("owner-1", rec.memory_id)

        # Verify deleted record is excluded from search and recall
        recalled = await self.service.recall("owner-1", "water")
        self.assertEqual(len(recalled), 0)

        searched = await self.service.search(MemoryQuery("owner-1", text="water"))
        self.assertEqual(len(searched), 0)

        # Get still reports status=deleted for audit
        deleted_rec = await self.service.get("owner-1", rec.memory_id)
        self.assertEqual(deleted_rec.status, "deleted")
        self.assertTrue(deleted_rec.archived)

    async def test_memory_expiry_and_maintenance(self) -> None:
        # Insert a temporary expired memory
        past = datetime.now(UTC) - timedelta(hours=2)
        rec = await self.service.create(MemoryCandidate(
            "owner-1", "Temporary Wi-Fi code is 1234", "fact",
        ))
        self.repo.update_memory("owner-1", rec.memory_id, valid_until=past)

        # Active search excludes expired memories
        results = await self.service.search(MemoryQuery("owner-1", text="Wi-Fi"))
        self.assertEqual(len(results), 0)

        # Maintain marks them as expired
        res = await self.service.maintain("owner-1")
        self.assertGreaterEqual(res["expired"], 1)

        updated = await self.service.get("owner-1", rec.memory_id)
        self.assertEqual(updated.status, "expired")
