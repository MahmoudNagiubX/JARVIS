"""Generic Venom node architecture without guessed network details."""

from __future__ import annotations

from datetime import UTC, datetime

from ..contracts import NodeDescriptor, NodeHealth, NodeRole, VenomNodePlan


class VenomNode:
    """Describes, but does not remotely deploy, the low-spec always-on node."""

    def __init__(self, descriptor: NodeDescriptor | None = None) -> None:
        self.descriptor = descriptor or NodeDescriptor(
            "venom", NodeRole.SERVER,
            frozenset({"postgresql", "memory_persistence", "scheduler", "proactive_watcher", "event_relay", "health_monitor", "backup_metadata"}),
            {"inference": "lightweight-only", "network": "unknown-until-deployment"},
        )
        self._health = NodeHealth(self.descriptor.node_id, False, datetime.now(UTC), "not_probed")

    def plan(self) -> VenomNodePlan:
        return VenomNodePlan(self.descriptor, tuple(sorted(self.descriptor.capabilities)), False)

    def health(self) -> NodeHealth:
        return self._health

    def set_health(self, available: bool, reason: str) -> NodeHealth:
        """Record externally supplied health evidence without probing remotely."""
        self._health = NodeHealth(self.descriptor.node_id, available, datetime.now(UTC), reason)
        return self._health
