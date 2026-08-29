"""SQLite backup, verification, and restore operations using SQLite itself."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .db import SQLiteDatabase


class SQLiteBackupService:
    """Explicit-path backups with integrity verification and no shell calls."""

    required_tables = frozenset({"owners", "events", "research_runs"})

    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def create(self, destination: str) -> dict[str, Any]:
        target = self._target(destination)
        if target == self._source_path():
            raise ValueError("backup destination must differ from source database")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise FileExistsError(str(target))
        connection = sqlite3.connect(str(target))
        try:
            self.database.connection.backup(connection)
            connection.commit()
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            connection.close()
        if integrity != "ok" or not self._schema_valid(connection_path=target):
            raise RuntimeError("backup integrity check failed")
        return {"path": str(target), "created_at": datetime.now(UTC).isoformat(), "integrity": integrity, "bytes": target.stat().st_size}

    @staticmethod
    def verify(path: str) -> dict[str, Any]:
        target = Path(path).expanduser().resolve(strict=True)
        if not target.is_file():
            raise ValueError("backup must be a file")
        connection = sqlite3.connect(str(target))
        try:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
        finally:
            connection.close()
        valid = integrity == "ok" and SQLiteBackupService.required_tables.issubset(tables)
        return {"path": str(target), "integrity": integrity, "tables": tables, "valid": valid}

    @staticmethod
    def restore(backup: str, destination: str, *, overwrite: bool = False) -> dict[str, Any]:
        source = Path(backup).expanduser().resolve(strict=True)
        target = Path(destination).expanduser().resolve(strict=False)
        if not source.is_file() or source == target:
            raise ValueError("restore paths must identify a backup file and a different destination")
        if not SQLiteBackupService.verify(str(source))["valid"]:
            raise ValueError("restore source is not a valid JARVIS backup")
        if target.exists() and not overwrite:
            raise FileExistsError(str(target))
        target.parent.mkdir(parents=True, exist_ok=True)
        source_connection = sqlite3.connect(str(source))
        target_connection = sqlite3.connect(str(target))
        try:
            source_connection.backup(target_connection)
            target_connection.commit()
            integrity = target_connection.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            source_connection.close()
            target_connection.close()
        if integrity != "ok":
            raise RuntimeError("restored database integrity check failed")
        return {"path": str(target), "integrity": integrity, "restored": True}

    @classmethod
    def _schema_valid(cls, connection_path: Path) -> bool:
        connection = sqlite3.connect(str(connection_path))
        try:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        finally:
            connection.close()
        return cls.required_tables.issubset(tables)

    def _source_path(self) -> Path | None:
        if self.database.path == ":memory:":
            return None
        return Path(self.database.path).expanduser().resolve(strict=False)

    @staticmethod
    def _target(path: str) -> Path:
        target = Path(path).expanduser().resolve(strict=False)
        if target.name in {"", ".", ".."}:
            raise ValueError("backup destination must be a file path")
        return target
