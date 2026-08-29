"""Application-facing use cases over the composed JARVIS runtime."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from ..authority.identity.service import EnrollmentGrant
from ..bootstrap import JarvisRuntime
from ..contracts import (
    DeviceIdentity,
    Goal,
    GoalStatus,
    Identity,
    MemoryCandidate,
    MemoryQuery,
    MemorySensitivity,
    WorldStateSnapshot,
    WorldStateQuery,
)
from ..models.routing import ModelRoute


@dataclass(frozen=True, slots=True)
class DemoPrincipal:
    identity: Identity
    device: DeviceIdentity
    credential: str | None = None


class CoreApplication:
    """Transport-neutral application service used by CLI and HTTP."""

    def __init__(self, runtime: JarvisRuntime) -> None:
        self.runtime = runtime

    async def ensure_demo_principal(self) -> DemoPrincipal:
        """Create a local test principal only when the local store is empty."""

        owner = self.runtime.repository.first_owner()
        if owner is None:
            identity = await self.runtime.identity.bootstrap_owner("Local Owner")
        else:
            identity_row = self.runtime.repository.first_identity(owner["id"])
            if identity_row is None:
                raise RuntimeError("owner exists without an active identity")
            identity = await self.runtime.identity.get_identity(identity_row["id"])
            if identity is None:
                raise RuntimeError("owner identity is unavailable")
        device_row = self.runtime.repository.first_device(identity.owner_id)
        if device_row is not None:
            device = await self.runtime.identity.device(device_row["id"])
            if device is None:
                raise RuntimeError("device is unavailable")
            return DemoPrincipal(identity, device)
        issued = await self.runtime.identity.create_enrollment(
            EnrollmentGrant(
                owner_id=identity.owner_id,
                display_name="Local CLI",
                device_kind="desktop",
                platform="windows",
                scopes=("tool.request",),
                capabilities=("computer.observe",),
                software_version="phase02",
            )
        )
        credential = await self.runtime.identity.redeem_enrollment(issued.code)
        device = await self.runtime.identity.device(credential.device_id)
        if device is None:
            raise RuntimeError("new device is unavailable")
        return DemoPrincipal(identity, device, credential.raw)

    async def principal(self, identity_id: str, device_id: str) -> DemoPrincipal | None:
        identity = await self.runtime.identity.get_identity(identity_id)
        device = await self.runtime.identity.device(device_id)
        if identity is None or device is None or identity.owner_id != device.owner_id:
            return None
        return DemoPrincipal(identity, device)

    async def authenticate_principal(
        self, credential: str, device_id: str, identity_id: str
    ) -> DemoPrincipal | None:
        device = await self.runtime.identity.authenticate(credential, device_id)
        identity = await self.runtime.identity.get_identity(identity_id)
        if device is None or identity is None or identity.owner_id != device.owner_id:
            return None
        return DemoPrincipal(identity, device, credential)

    async def send_message(
        self,
        text: str,
        identity: Identity,
        device: DeviceIdentity,
        *,
        session_id: str | None = None,
        conversation_id: str | None = None,
        client_message_id: str | None = None,
    ) -> dict[str, Any]:
        outcome = await self.runtime.agent.process_text(
            text,
            identity,
            device,
            session_id=session_id,
            conversation_id=conversation_id,
            client_message_id=client_message_id,
        )
        return {
            "run_id": outcome.run_id,
            "conversation_id": outcome.conversation_id,
            "session_id": outcome.session_id,
            "state": outcome.state.value,
            "response": outcome.response,
            "pending_approval_id": outcome.pending_approval_id,
            "assistant_message_id": outcome.assistant_message_id,
            "error_code": outcome.error_code,
            "replayed": outcome.replayed,
        }

    async def resume_approval(
        self,
        approval_id: str,
        run_id: str,
        identity: Identity,
        device: DeviceIdentity,
        approved: bool,
        decided_by: str,
    ) -> dict[str, Any]:
        run = self.runtime.repository.run(run_id)
        if run is None or run.pending_approval_id != approval_id:
            raise ValueError("approval does not belong to run")
        outcome = await self.runtime.agent.resume(
            run_id,
            identity,
            device,
            decided_by,
            approved=approved,
        )
        return {
            "approval_id": approval_id,
            "run_id": outcome.run_id,
            "state": outcome.state.value,
            "response": outcome.response,
            "error_code": outcome.error_code,
        }

    async def cancel(
        self,
        run_id: str,
        identity: Identity | None = None,
        device: DeviceIdentity | None = None,
    ) -> dict[str, Any] | None:
        run = self.runtime.repository.run(run_id)
        if run is None:
            return None
        if identity is not None and device is not None:
            if run.request_device_id != device.device_id or identity.owner_id != device.owner_id:
                raise ValueError("run owner/device binding mismatch")
        outcome = await self.runtime.agent.cancel(run_id)
        if outcome is None:
            return None
        return {"run_id": outcome.run_id, "state": outcome.state.value}

    async def health(self) -> dict[str, Any]:
        model = await self.runtime.models.health(ModelRoute.GENERAL_REASONING)
        return {
            "service": self.runtime.config.service_name,
            "environment": self.runtime.config.environment,
            "state": self.runtime.state.value,
            "database": "closed" if self.runtime.database.closed else "open",
            "model": asdict(model),
            "offline": asdict(self.runtime.offline.state),
            "internet": asdict(self.runtime.offline.state),
            "local_model": {"available": model.available, "provider": model.provider, "reason": model.reason},
            "venom": asdict(self.runtime.venom.health()),
        }

    # Phase 03 application use cases ------------------------------------
    async def list_memory(
        self,
        owner_id: str,
        *,
        text: str = "",
        category: str | None = None,
        source: str | None = None,
        tags: tuple[str, ...] = (),
        include_archived: bool = False,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        records = await self.runtime.memory.search(
            MemoryQuery(owner_id, text, category, source, tags, ("active",), include_archived, limit)
        )
        return [asdict(record) for record in records]

    async def create_memory(
        self,
        owner_id: str,
        content: str,
        category: str = "fact",
        *,
        structured_data: dict[str, object] | None = None,
        source: str = "user",
        source_reference: str | None = "api",
        confidence: float = 1.0,
        sensitivity: str = MemorySensitivity.PERSONAL.value,
        tags: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        record = await self.runtime.memory.create(
            MemoryCandidate(owner_id, content, category, source, source_reference, structured_data or {}, confidence, sensitivity, tags)
        )
        if record is None:
            raise ValueError("memory rejected by policy")
        return asdict(record)

    async def get_memory(self, owner_id: str, memory_id: str) -> dict[str, Any] | None:
        record = await self.runtime.memory.get(owner_id, memory_id)
        return asdict(record) if record else None

    async def update_memory(self, owner_id: str, memory_id: str, values: dict[str, object]) -> dict[str, Any]:
        allowed = {"content", "category", "structured_data", "tags", "sensitivity"}
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f"unsupported memory fields: {sorted(unknown)}")
        record = await self.runtime.memory.update(
            owner_id,
            memory_id,
            content=values.get("content") if isinstance(values.get("content"), str) else None,
            category=values.get("category") if isinstance(values.get("category"), str) else None,
            structured_data=values.get("structured_data") if isinstance(values.get("structured_data"), dict) else None,
            tags=tuple(values["tags"]) if isinstance(values.get("tags"), list) and all(isinstance(item, str) for item in values["tags"]) else None,
            sensitivity=values.get("sensitivity") if isinstance(values.get("sensitivity"), str) else None,
        )
        return asdict(record)

    async def delete_memory(self, owner_id: str, memory_id: str) -> None:
        await self.runtime.memory.delete(owner_id, memory_id)

    async def forget_memory_category(self, owner_id: str, category: str) -> int:
        return await self.runtime.memory.forget_category(owner_id, category)

    async def pin_memory(self, owner_id: str, memory_id: str, pinned: bool = True) -> dict[str, Any]:
        return asdict(await self.runtime.memory.pin(owner_id, memory_id, pinned))

    async def archive_memory(self, owner_id: str, memory_id: str, archived: bool = True) -> dict[str, Any]:
        return asdict(await self.runtime.memory.archive(owner_id, memory_id, archived))

    async def world_state(self, owner_id: str, *, key_prefix: str | None = None, include_expired: bool = False) -> dict[str, Any]:
        snapshot = await self.runtime.world_state.snapshot(owner_id)
        if key_prefix is not None or include_expired:
            facts = await self.runtime.world_state.facts(WorldStateQuery(owner_id, key_prefix, include_expired))
            snapshot = WorldStateSnapshot(snapshot.snapshot_id, snapshot.created_at, snapshot.observations, {item.key: item.value for item in facts}, snapshot.conflicts)
        return asdict(snapshot)

    async def world_conflicts(self, owner_id: str) -> list[dict[str, Any]]:
        return [asdict(item) for item in await self.runtime.world_state.conflicts(owner_id)]

    async def list_goals(self, owner_id: str, statuses: tuple[str, ...] = ()) -> list[dict[str, Any]]:
        return [asdict(item) for item in await self.runtime.goals.list(owner_id, statuses)]

    async def create_goal(self, owner_id: str, values: dict[str, object]) -> dict[str, Any]:
        title = str(values.get("title") or values.get("description") or values.get("statement") or "").strip()
        description = str(values.get("description") or values.get("statement") or title).strip()
        status = GoalStatus(str(values.get("status", GoalStatus.DRAFT.value)))
        target_date = self._parse_datetime(values.get("target_date"))
        goal = await self.runtime.goals.create(
            Goal(
                str(values.get("goal_id", "")), owner_id, description, status, None, dict(values.get("metadata", {})) if isinstance(values.get("metadata"), dict) else {},
                title, description, int(values.get("priority", 0)), target_date,
                dict(values.get("constraints", {})) if isinstance(values.get("constraints"), dict) else {},
                dict(values.get("budget", {})) if isinstance(values.get("budget"), dict) else {},
                tuple(str(item) for item in values.get("plan", []) if isinstance(item, str)),
                (), tuple(str(item) for item in values.get("dependencies", []) if isinstance(item, str)), (),
                values.get("next_action") if isinstance(values.get("next_action"), str) else None, None,
                tuple(str(item) for item in values.get("completion_criteria", []) if isinstance(item, str)),
            )
        )
        return asdict(goal)

    async def update_goal(self, owner_id: str, goal_id: str, values: dict[str, object]) -> dict[str, Any]:
        values = dict(values)
        status = values.pop("status", None)
        if status is not None:
            goal = await self.runtime.goals.transition(goal_id, GoalStatus(str(status)), owner_id)
            if goal is None:
                raise KeyError(goal_id)
        goal = await self.runtime.goals.update(
            owner_id, goal_id,
            title=values.get("title") if isinstance(values.get("title"), str) else None,
            description=values.get("description") if isinstance(values.get("description"), str) else None,
            priority=int(values["priority"]) if "priority" in values else None,
            target_date=self._parse_datetime(values.get("target_date")) if "target_date" in values else None,
            constraints=values.get("constraints") if isinstance(values.get("constraints"), dict) else None,
            budget=values.get("budget") if isinstance(values.get("budget"), dict) else None,
            next_action=values.get("next_action") if isinstance(values.get("next_action"), str) else None,
            completion_criteria=tuple(item for item in values.get("completion_criteria", ()) if isinstance(item, str)) if "completion_criteria" in values else None,
        )
        return asdict(goal)

    async def control_goal(self, owner_id: str, goal_id: str, action: str) -> dict[str, Any]:
        handlers = {"pause": self.runtime.goals.pause, "resume": self.runtime.goals.resume, "cancel": self.runtime.goals.cancel, "complete": self.runtime.goals.complete, "activate": self.runtime.goals.activate}
        if action not in handlers:
            raise ValueError("unsupported goal action")
        goal = await handlers[action](owner_id, goal_id)
        if goal is None:
            raise KeyError(goal_id)
        return asdict(goal)

    async def proactive_findings(self, owner_id: str, active_only: bool = False) -> list[dict[str, Any]]:
        return [asdict(item) for item in await self.runtime.proactive.list(owner_id, active_only)]

    async def acknowledge_finding(self, owner_id: str, finding_id: str) -> dict[str, Any]:
        return asdict(await self.runtime.proactive.acknowledge(owner_id, finding_id))

    async def personalization_profile(self, owner_id: str) -> dict[str, Any]:
        return asdict(await self.runtime.personalization.get(owner_id))

    async def update_personalization(self, owner_id: str, values: dict[str, object], source: str = "user") -> dict[str, Any]:
        return asdict(await self.runtime.personalization.patch(owner_id, values, source))

    async def context(self, identity: Identity, device: DeviceIdentity, query: str = "") -> dict[str, Any]:
        return (await self.runtime.context.assemble(identity, device, query)).as_dict()

    @staticmethod
    def _parse_datetime(value: object) -> datetime | None:
        if value is None or value == "":
            return None
        if not isinstance(value, str):
            raise ValueError("datetime must be an ISO string")
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    def events(self, correlation_id: str | None = None) -> list[dict[str, Any]]:
        return self.runtime.repository.events(correlation_id)

    async def approval(self, approval_id: str) -> dict[str, Any] | None:
        decision = await self.runtime.approval.get(approval_id)
        if decision is None:
            return None
        return {
            "approval_id": decision.approval_id,
            "status": decision.status.value,
            "decided_by": decision.decided_by,
            "decided_at": decision.decided_at.isoformat() if decision.decided_at else None,
            "reason": decision.reason,
        }
