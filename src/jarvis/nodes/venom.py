"""Generic Venom node architecture and infrastructure health services."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..contracts import (
    NodeDescriptor,
    NodeHealth,
    NodeRole,
    NodeStatus,
    VenomDetailedHealth,
    VenomNodePlan,
    VenomServiceHealth,
    VenomStorageHealth,
)


class VenomNode:
    """Describes and monitors the Linux infrastructure node without creating a second authority."""

    DEFAULT_CAPABILITIES = frozenset({
        "node.health",
        "node.service",
        "mqtt_broker",
        "backup_receiver",
        "health_monitor",
        "event_relay",
        "ha_bridge",
    })

    def __init__(
        self,
        descriptor: NodeDescriptor | None = None,
        *,
        config: Mapping[str, object] | None = None,
    ) -> None:
        self.descriptor = descriptor or NodeDescriptor(
            "venom",
            NodeRole.SERVER,
            self.DEFAULT_CAPABILITIES,
            {"inference": "lightweight-only", "platform": "linux", "os": "ubuntu-server"},
        )
        self._config = dict(config or {})
        self._status = NodeStatus.NOT_CONFIGURED.value
        self._health = NodeHealth(self.descriptor.node_id, False, datetime.now(UTC), "not_probed")
        self._services: dict[str, VenomServiceHealth] = {
            "jarvis-venom": VenomServiceHealth("jarvis-venom", False, "inactive", datetime.now(UTC)),
            "mosquitto": VenomServiceHealth("mosquitto", False, "inactive", datetime.now(UTC)),
        }
        self._capabilities: dict[str, str] = {
            "mqtt_broker": "not_configured",
            "backup_receiver": "not_configured",
            "event_relay": "not_configured",
            "ha_bridge": "not_configured",
        }
        self._storage: VenomStorageHealth | None = None
        self._version = "phase17"
        self._last_heartbeat: datetime | None = None

    @property
    def status(self) -> str:
        return self._status

    @property
    def version(self) -> str:
        return self._version

    @property
    def capabilities(self) -> dict[str, str]:
        return dict(self._capabilities)

    def plan(self) -> VenomNodePlan:
        return VenomNodePlan(self.descriptor, tuple(sorted(self.descriptor.capabilities)), False)

    def health(self) -> NodeHealth:
        return self._health

    def detailed_health(self) -> VenomDetailedHealth:
        return VenomDetailedHealth(
            node_id=self.descriptor.node_id,
            status=self._status,
            available=self._health.available,
            checked_at=self._health.checked_at,
            reason=self._health.reason,
            version=self._version,
            storage=self._storage,
            services=tuple(self._services.values()),
            mqtt_healthy=self._services.get("mosquitto", VenomServiceHealth("mosquitto", False, "inactive", datetime.now(UTC))).active,
            ha_bridge_healthy=bool(self._config.get("ha_bridge_enabled", False) and self._health.available),
            backup_receive_healthy=bool(self._storage and self._storage.status == "healthy"),
            capabilities=dict(self._capabilities),
        )

    def set_health(self, available: bool, reason: str) -> NodeHealth:
        """Record externally supplied health evidence without probing remotely."""
        now = datetime.now(UTC)
        self._health = NodeHealth(self.descriptor.node_id, available, now, reason)
        if available:
            self._status = NodeStatus.ONLINE.value
            self._last_heartbeat = now
        elif self._status != NodeStatus.NOT_CONFIGURED.value:
            self._status = NodeStatus.OFFLINE.value if reason in {"offline", "disconnected"} else NodeStatus.DEGRADED.value
        return self._health

    def record_heartbeat(self, timestamp: datetime | None = None, metadata: Mapping[str, object] | None = None) -> NodeHealth:
        now = timestamp or datetime.now(UTC)
        self._last_heartbeat = now
        self._status = NodeStatus.ONLINE.value
        reason = "heartbeat_received"
        if metadata and "details" in metadata and str(metadata["details"]).strip():
            reason = str(metadata["details"]).strip()
        self._health = NodeHealth(self.descriptor.node_id, True, now, reason)
        if metadata:
            if "storage" in metadata and isinstance(metadata["storage"], dict):
                st = metadata["storage"]
                self.update_storage_health(
                    int(st.get("total_bytes", 0)),
                    int(st.get("free_bytes", 0)),
                    int(st.get("used_bytes", 0)),
                )
            if "services" in metadata and isinstance(metadata["services"], list):
                for s in metadata["services"]:
                    if isinstance(s, dict) and "name" in s:
                        self.update_service_health(
                            str(s["name"]),
                            bool(s.get("active", False)),
                            str(s.get("status", "unknown")),
                        )
            if "capabilities" in metadata and isinstance(metadata["capabilities"], dict):
                for k, v in metadata["capabilities"].items():
                    self._capabilities[str(k)] = str(v)
        return self._health

    def update_storage_health(self, total_bytes: int, free_bytes: int, used_bytes: int) -> VenomStorageHealth:
        usage_pct = (used_bytes / total_bytes * 100.0) if total_bytes > 0 else 0.0
        status = "healthy" if usage_pct < 85.0 else "warning" if usage_pct < 95.0 else "critical"
        self._storage = VenomStorageHealth(total_bytes, free_bytes, used_bytes, round(usage_pct, 2), status)
        return self._storage

    def update_service_health(self, service_name: str, active: bool, status: str) -> VenomServiceHealth:
        record = VenomServiceHealth(service_name, active, status, datetime.now(UTC))
        self._services[service_name] = record
        return record

    def verify_backup(self, backup_file_path: str | Path, expected_sha256: str | None = None) -> dict[str, object]:
        """Verify the integrity and SQLite header of a received backup file on Venom."""
        path = Path(backup_file_path)
        if not path.is_file():
            return {"valid": False, "reason": "backup_file_not_found"}
        try:
            content = path.read_bytes()
            if len(content) < 100:
                return {"valid": False, "reason": "backup_file_too_small"}
            if not content.startswith(b"SQLite format 3\000"):
                return {"valid": False, "reason": "invalid_sqlite_header"}
            actual_sha256 = hashlib.sha256(content).hexdigest()
            if expected_sha256 and actual_sha256.lower() != expected_sha256.lower():
                return {"valid": False, "reason": "checksum_mismatch", "actual_sha256": actual_sha256}
            return {
                "valid": True,
                "file_size": len(content),
                "sha256": actual_sha256,
                "verified_at": datetime.now(UTC).isoformat(),
            }
        except Exception as exc:
            return {"valid": False, "reason": f"verification_error:{exc.__class__.__name__}"}

    def deployment_status(self) -> str:
        """Report physical deployment status without fabricating credentials or connection."""
        host = os.environ.get("JARVIS_VENOM_HOST") or self._config.get("host")
        if not host:
            return "BLOCKED_WAITING_FOR_CONNECTION_DETAILS"
        return self._status
