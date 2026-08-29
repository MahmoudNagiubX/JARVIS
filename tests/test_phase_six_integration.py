from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from jarvis.bootstrap import create_runtime
from jarvis.config import JarvisConfig
from jarvis.contracts import DeviceIdentity, ResearchPlan, ResearchRequest, ResearchRun, ResearchStep
from jarvis.experience.websocket import accept_key, text_frame
from jarvis.models.gateway import ModelGateway
from jarvis.models.probes import LocalModelCapabilityProbe
from jarvis.models.routing import ModelRoute
from jarvis.persistence.adapters import PostgresDatabase
from jarvis.persistence.backup import SQLiteBackupService
from jarvis.persistence.db import SQLiteDatabase
from jarvis.runtime.lifecycle import RuntimeLifecycle
from jarvis.security import redact


class _Cursor:
    def execute(self, statement: str) -> None:
        self.statement = statement

    def fetchone(self) -> tuple[int]:
        return (1,)


class _Connection:
    def __init__(self) -> None:
        self.commits = 0
        self.closed = False

    def cursor(self) -> _Cursor:
        return _Cursor()

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class PhaseSixIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_research_ledger_survives_restart_and_reconciles_transient_work(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            database_path = str(Path(folder) / "jarvis.sqlite3")
            runtime = create_runtime(JarvisConfig(database_path=database_path))
            await runtime.start()
            owner = await runtime.identity.bootstrap_owner("Durable Owner")
            device = DeviceIdentity("durable-device", owner.owner_id, "desktop", "windows", frozenset({"research.local"}), frozenset({"tool.request"}))
            completed = await runtime.research.start(
                ResearchRequest("durable evidence", owner.owner_id, device.device_id), owner, device
            )
            self.assertEqual(completed.status, "completed")
            stale = ResearchRun(
                "research-stale", ResearchRequest("stale", owner.owner_id, device.device_id),
                ResearchPlan(("search local documents",)), "running",
                (ResearchStep("step-1", "search local documents", "running"),),
                created_at=datetime.now(UTC),
            )
            runtime.repository.insert_research_run(stale)
            lifecycle = RuntimeLifecycle(runtime)
            await lifecycle.stop()

            restarted = create_runtime(JarvisConfig(database_path=database_path))
            await restarted.start()
            try:
                recovered = restarted.research.get("research-stale", owner.owner_id)
                durable = restarted.research.get(completed.run_id, owner.owner_id)
                self.assertIsNotNone(recovered)
                self.assertEqual(recovered.status if recovered else None, "failed")
                self.assertEqual(recovered.error_code if recovered else None, "process_restarted")
                self.assertIsNotNone(durable)
                self.assertEqual(durable.status if durable else None, "completed")
            finally:
                await restarted.shutdown()

    async def test_backup_restore_model_probe_and_lifecycle_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            source_path = str(Path(folder) / "source.sqlite3")
            backup_path = str(Path(folder) / "backup.sqlite3")
            restore_path = str(Path(folder) / "restore.sqlite3")
            database = SQLiteDatabase(source_path)
            database.connection.execute("INSERT INTO owners VALUES ('owner-test', 'Test', 'active', '2026-01-01T00:00:00+00:00')")
            database.connection.commit()
            service = SQLiteBackupService(database)
            created = service.create(backup_path)
            self.assertEqual(created["integrity"], "ok")
            self.assertTrue(SQLiteBackupService.verify(backup_path)["valid"])
            self.assertTrue(SQLiteBackupService.restore(backup_path, restore_path)["restored"])
            restored = SQLiteDatabase(restore_path)
            try:
                self.assertEqual(restored.connection.execute("SELECT COUNT(*) FROM owners").fetchone()[0], 1)
            finally:
                restored.close()
                database.close()

        runtime = create_runtime(JarvisConfig(environment="test"))
        lifecycle = RuntimeLifecycle(runtime)
        started = await lifecycle.start()
        self.assertEqual(started.state, "ready")
        probe = await LocalModelCapabilityProbe(ModelGateway(runtime.config)).run(ModelRoute.GENERAL_REASONING, exercise_generation=True)
        self.assertTrue(probe.available)
        stopped = await lifecycle.stop()
        self.assertEqual(stopped.state, "stopped")

    async def test_postgres_reconnect_retention_redaction_and_websocket_framing(self) -> None:
        connections = [_Connection(), _Connection()]

        def factory() -> _Connection:
            return connections.pop(0)

        database = PostgresDatabase(factory)
        self.assertTrue(database.health().available)
        self.assertTrue(database.reconnect().available)
        database.close()
        self.assertFalse(database.health().available)

        runtime = create_runtime(JarvisConfig(environment="test"))
        await runtime.start()
        try:
            before = datetime.now(UTC) + timedelta(seconds=1)
            event = runtime.repository.event_count()
            dry_run = runtime.repository.prune_events(before)
            self.assertEqual(dry_run["deleted"], 0)
            self.assertEqual(runtime.repository.event_count(), event)
            value = redact({"credential": "secret", "nested": {"token": "x", "safe": "ok"}})
            self.assertEqual(value["credential"], "[redacted]")
            self.assertEqual(value["nested"]["safe"], "ok")
        finally:
            await runtime.shutdown()
        self.assertGreater(len(text_frame({"ok": True})), 2)
        self.assertEqual(accept_key("dGhlIHNhbXBsZSBub25jZQ=="), "s3pPLMBiTxaQ9kYGzzhZRbK+xOo=")


if __name__ == "__main__":
    unittest.main()
