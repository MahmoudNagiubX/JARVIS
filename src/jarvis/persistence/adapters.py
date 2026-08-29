"""Database adapter contracts and an optional injected PostgreSQL adapter.

The product package intentionally has no psycopg dependency. Applications can
provide a DB-API connection or factory from their local PostgreSQL deployment;
the adapter supplies transaction and health boundaries without importing a
driver or connecting during module import.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class DatabaseHealth:
    backend: str
    available: bool
    checked_at: datetime
    reason: str


class DatabaseAdapter(Protocol):
    backend: str

    @contextmanager
    def transaction(self) -> Iterator[Any]: ...

    def health(self) -> DatabaseHealth: ...

    def close(self) -> None: ...


class PostgresDatabase:
    """Use an already-configured PostgreSQL DB-API connection.

    `connection_factory` is injected by deployment code, keeping the core
    free-only and offline-capable. SQL migrations live beside the SQLite
    marker and use PostgreSQL-native JSONB/vector types when deployed.
    """

    backend = "postgresql"

    def __init__(self, connection_factory: Callable[[], Any]) -> None:
        self._connection_factory = connection_factory
        self.connection = connection_factory()
        self._lock = RLock()
        self._closed = False

    @contextmanager
    def transaction(self) -> Iterator[Any]:
        if self._closed:
            raise RuntimeError("database is closed")
        with self._lock:
            try:
                yield self.connection
                self.connection.commit()
            except Exception:
                self.connection.rollback()
                raise

    def health(self) -> DatabaseHealth:
        now = datetime.now(UTC)
        if self._closed:
            return DatabaseHealth(self.backend, False, now, "closed")
        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
        except Exception as exc:
            return DatabaseHealth(self.backend, False, now, exc.__class__.__name__)
        return DatabaseHealth(self.backend, True, now, "ready")

    def close(self) -> None:
        if not self._closed:
            with self._lock:
                self.connection.close()
                self._closed = True
