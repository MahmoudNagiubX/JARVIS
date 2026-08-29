"""Owner-local daily-window evaluation with a safe host-timezone fallback."""
from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def in_time_window(start: str | None, end: str | None, *, now: datetime, timezone_name: str | None = None) -> bool:
    if not start or not end:
        return True
    try:
        zone = ZoneInfo(timezone_name) if timezone_name else now.astimezone().tzinfo
        current = now.astimezone(zone)
        begin, finish = time.fromisoformat(start), time.fromisoformat(end)
    except (TypeError, ValueError, ZoneInfoNotFoundError):
        return False
    value = current.time().replace(tzinfo=None)
    return begin <= value <= finish if begin <= finish else value >= begin or value <= finish
