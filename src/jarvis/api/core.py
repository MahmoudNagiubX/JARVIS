"""Application-facing use cases over the composed JARVIS runtime."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from ..authority.identity.service import EnrollmentGrant
from ..bootstrap import JarvisRuntime
from ..contracts import DeviceIdentity, Identity
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
        }

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
