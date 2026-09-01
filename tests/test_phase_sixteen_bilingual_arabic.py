"""Phase 16: Bilingual Arabic & Egyptian technical phrase memory extraction and retrieval tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from jarvis.bus import InMemoryEventBus
from jarvis.contracts import (
    MemoryCandidate,
    MemoryQuery,
)
from jarvis.memory.extractors import DeterministicMemoryExtractor
from jarvis.memory.retrieval import KeywordMemoryRetriever
from jarvis.memory.service import DurableMemoryService
from jarvis.persistence.db import SQLiteDatabase
from jarvis.persistence.repositories import RuntimeRepository


class PhaseSixteenBilingualArabicTests(unittest.IsolatedAsyncioTestCase):
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

    def test_arabic_deterministic_extraction(self) -> None:
        extractor = DeterministicMemoryExtractor()

        # 1. Arabic project tech (Egyptian Arabic: افتكر إن المشروع ده بيستخدم PostgreSQL)
        c1 = extractor.extract_sync("owner-1", "افتكر إن المشروع ده بيستخدم PostgreSQL")
        self.assertGreaterEqual(len(c1), 1)
        self.assertEqual(c1[0].category, "project")
        self.assertIn("project_", c1[0].structured_data.get("key", ""))
        self.assertIn("PostgreSQL", str(c1[0].structured_data.get("technology", "")))

        # 2. Arabic Goal (الهدف بتاعي أخلص الـdocumentation الجمعة)
        c2 = extractor.extract_sync("owner-1", "الهدف بتاعي أخلص الـdocumentation الجمعة")
        self.assertGreaterEqual(len(c2), 1)
        self.assertEqual(c2[0].category, "goal")

        # 3. Arabic Task / Deadline (فكرني قبل الـdeadline بيوم)
        c3 = extractor.extract_sync("owner-1", "فكرني قبل الـdeadline بيوم")
        self.assertGreaterEqual(len(c3), 1)
        self.assertEqual(c3[0].category, "task")

        # 4. Arabic Preferred Editor (الـeditor المفضل هو PyCharm)
        c4 = extractor.extract_sync("owner-1", "الـeditor المفضل هو PyCharm")
        self.assertGreaterEqual(len(c4), 1)
        self.assertEqual(c4[0].category, "preference")
        self.assertEqual(c4[0].structured_data.get("key"), "preferred_editor")
        self.assertEqual(c4[0].structured_data.get("value"), "PyCharm")

        # 5. Arabic Name (اسمي هو محمود)
        c5 = extractor.extract_sync("owner-1", "اسمي هو محمود")
        self.assertGreaterEqual(len(c5), 1)
        self.assertEqual(c5[0].category, "profile")
        self.assertEqual(c5[0].structured_data.get("value"), "محمود")

    async def test_arabic_normalization_and_retrieval(self) -> None:
        # Create memory with Arabic text and mixed English
        await self.service.create(MemoryCandidate(
            "owner-1", "مشروع فينيكس بيستخدم قاعدة بيانات PostgreSQL للـbackend", "project",
            tags=("backend", "database"),
        ))
        await self.service.create(MemoryCandidate(
            "owner-1", "المحرر المفضل للتطوير هو VS Code", "preference",
            tags=("tools",),
        ))

        # Query with alef variation: إفتكر / فينيكس / بوستجريس
        results1 = await self.service.search(MemoryQuery("owner-1", text="فينيكس"))
        self.assertEqual(len(results1), 1)
        self.assertIn("PostgreSQL", results1[0].content)

        # Query in English for the database
        results2 = await self.service.search(MemoryQuery("owner-1", text="PostgreSQL"))
        self.assertEqual(len(results2), 1)

        # Query with alef variation (المحرر vs محرر)
        results3 = await self.service.search(MemoryQuery("owner-1", text="المحرر المفضل"))
        self.assertEqual(len(results3), 1)
        self.assertIn("VS Code", results3[0].content)
