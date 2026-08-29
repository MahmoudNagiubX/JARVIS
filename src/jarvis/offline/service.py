"""Explicit online/offline policy with local capability continuity."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from ..contracts import ConnectivityState, OfflineCapabilityDecision


class OfflineModeService:
    def __init__(self, probe: Callable[[], bool | Awaitable[bool]] | None = None) -> None:
        self._probe = probe
        self._state = ConnectivityState(True, None, "unverified")

    @property
    def state(self) -> ConnectivityState:
        return self._state

    async def refresh(self) -> ConnectivityState:
        if self._probe is None:
            return self._state
        result = self._probe()
        if inspect.isawaitable(result):
            result = await result
        return self.set_online(bool(result), "probe")

    def set_online(self, online: bool, source: str = "runtime") -> ConnectivityState:
        now = datetime.now(UTC) if online else self._state.last_seen
        self._state = ConnectivityState(online, now, source)
        return self._state

    def can_use(self, capability: str) -> OfflineCapabilityDecision:
        cloud_only = capability.startswith(("cloud.", "paid.", "remote."))
        if not self._state.online and cloud_only:
            return OfflineCapabilityDecision(capability, False, "offline_cloud_capability_unavailable")
        return OfflineCapabilityDecision(capability, True, "local_capability_available" if not self._state.online else "online")
