"""Owner/device/session-bound in-memory perception cache."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any


@dataclass(frozen=True, slots=True)
class CachedObservation:
    owner_id: str
    device_id: str
    session_id: str
    value: Any
    captured_at: datetime
    expires_at: datetime


class ObservationCache:
    TTL_SECONDS = 60
    MAX_PER_OWNER = 8
    MAX_TOTAL = 32

    def __init__(self, *, ttl_seconds: int = TTL_SECONDS, max_per_owner: int = MAX_PER_OWNER, max_total: int = MAX_TOTAL) -> None:
        if ttl_seconds <= 0 or max_per_owner <= 0 or max_total <= 0:
            raise ValueError("observation cache limits must be positive")
        self.ttl_seconds = ttl_seconds
        self.max_per_owner = max_per_owner
        self.max_total = max_total
        self._items: dict[str, CachedObservation] = {}

    def put(self, owner_id: str, device_id: str, session_id: str, value: Any, *, now: datetime | None = None) -> str:
        observation_id = getattr(value, "observation_id", None) or getattr(value, "snapshot_id", None)
        if not isinstance(observation_id, str) or not observation_id.strip():
            raise ValueError("cached value requires an observation id")
        current = _aware(now or datetime.now(UTC))
        self.prune(current)
        self._items[observation_id] = CachedObservation(owner_id, device_id, session_id, value, current, current + timedelta(seconds=self.ttl_seconds))
        owner_items = [item for item in self._items.values() if item.owner_id == owner_id]
        owner_items.sort(key=lambda item: item.captured_at)
        for item in owner_items[:-self.max_per_owner]:
            self._items.pop(_value_id(item.value), None)
        while len(self._items) > self.max_total:
            oldest = min(self._items.values(), key=lambda item: item.captured_at)
            self._items.pop(_value_id(oldest.value), None)
        return observation_id

    def get(self, owner_id: str, device_id: str, session_id: str, observation_id: str, *, now: datetime | None = None) -> Any | None:
        current = _aware(now or datetime.now(UTC))
        self.prune(current)
        item = self._items.get(observation_id)
        if item is None or item.owner_id != owner_id or item.device_id != device_id or item.session_id != session_id:
            return None
        return item.value

    def latest(self, owner_id: str, device_id: str, session_id: str, *, now: datetime | None = None) -> Any | None:
        current = _aware(now or datetime.now(UTC))
        self.prune(current)
        values = [item for item in self._items.values() if item.owner_id == owner_id and item.device_id == device_id and item.session_id == session_id]
        return max(values, key=lambda item: item.captured_at).value if values else None

    def expires_at(self, observation_id: str) -> datetime | None:
        item = self._items.get(observation_id)
        return item.expires_at if item else None

    def prune(self, now: datetime | None = None) -> int:
        current = _aware(now or datetime.now(UTC))
        expired = [key for key, item in self._items.items() if item.expires_at <= current]
        for key in expired:
            self._items.pop(key, None)
        return len(expired)

    def clear(self) -> None:
        self._items.clear()

    def __len__(self) -> int:
        return len(self._items)


def _value_id(value: Any) -> str:
    return str(getattr(value, "observation_id", None) or getattr(value, "snapshot_id"))


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("observation cache time must be timezone-aware")
    return value.astimezone(UTC)
