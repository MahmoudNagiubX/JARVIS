"""Expose only explicitly registered, currently available capabilities."""

from __future__ import annotations

from collections.abc import Iterable

from ..contracts import CapabilityDescriptor


class CapabilityRegistry:
    def __init__(self) -> None:
        self._items: dict[str, CapabilityDescriptor] = {}

    def register(self, descriptor: CapabilityDescriptor) -> None:
        if not descriptor.capability_id.strip() or not descriptor.provider.strip():
            raise ValueError("capability id and provider are required")
        self._items[descriptor.capability_id] = descriptor

    def set_available(self, capability_id: str, available: bool) -> CapabilityDescriptor:
        current = self._items.get(capability_id)
        if current is None:
            raise KeyError(capability_id)
        updated = CapabilityDescriptor(current.capability_id, current.provider, current.device_id, available, current.risk, current.requires_internet, current.requires_local_network, current.requires_device_online, current.permission, current.metadata)
        self._items[capability_id] = updated
        return updated

    def get(self, capability_id: str, *, available_only: bool = False) -> CapabilityDescriptor | None:
        descriptor = self._items.get(capability_id)
        if available_only and (descriptor is None or not descriptor.available):
            return None
        return descriptor

    def list(self, *, available_only: bool = True, device_id: str | None = None) -> tuple[CapabilityDescriptor, ...]:
        values: Iterable[CapabilityDescriptor] = self._items.values()
        if available_only:
            values = (item for item in values if item.available)
        if device_id is not None:
            values = (item for item in values if item.device_id in {None, device_id})
        return tuple(sorted(values, key=lambda item: item.capability_id))

    def consistency(self) -> tuple[dict[str, object], ...]:
        """Return an inspectable truth table for capability advertisements."""
        return tuple({
            "capability_id": item.capability_id,
            "provider": item.provider,
            "available": item.available,
            "risk": item.risk,
            "requires_internet": item.requires_internet,
            "requires_local_network": item.requires_local_network,
            "requires_device_online": item.requires_device_online,
            "reason": item.metadata.get("reason") if isinstance(item.metadata, dict) else None,
        } for item in self.list(available_only=False))
