"""Application-facing use cases over the composed JARVIS runtime."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from ..authority.identity.service import EnrollmentGrant
from ..bootstrap import JarvisRuntime
from ..contracts import (
    BrowserAction,
    ClientSession,
    ComputerAction,
    ComputerResult,
    DeviceIdentity,
    DeviceRecord,
    Goal,
    GoalStatus,
    HomeAction,
    Identity,
    EngineeringAction,
    EngineeringWorkspace,
    ResearchRequest,
    VisualRegion,
    MemoryCandidate,
    MemoryQuery,
    MemorySensitivity,
    WorldStateSnapshot,
    WorldStateQuery,
    DeviceHeartbeat,
    DeviceRole,
    DeviceStatus,
)
from ..devices.satellite.contracts import CommandObservation, SatelliteHeartbeat, SatelliteHello
from ..models.routing import ModelRoute
from ..contracts import Mission, MissionBudget, MissionStatus
from ..automation import AutomationAction, AutomationCondition, AutomationRule, AutomationTrigger


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
                capabilities=("computer.observe", "perception.screen"),
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
        device_row = self.runtime.repository.device(device_id)
        device = await self.runtime.identity.device(device_id)
        if identity is None or device is None or device_row is None or device_row.get("status") != "active" or identity.owner_id != device.owner_id:
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

    async def list_conversations(self, owner_id: str) -> list[dict[str, Any]]:
        return [asdict(item) for item in self.runtime.repository.conversations(owner_id)]

    async def conversation_messages(self, owner_id: str, conversation_id: str) -> list[dict[str, Any]] | None:
        conversation = self.runtime.repository.conversation(conversation_id)
        if conversation is None or conversation.owner_id != owner_id:
            return None
        return [asdict(item) for item in self.runtime.repository.messages(conversation_id)]

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
            "local_model": {
                "available": model.available,
                "provider": model.provider,
                "model_alias": model.model,
                "latency_ms": model.latency_ms,
                "reason": model.reason,
            },
            "venom": asdict(self.runtime.venom.health()),
            "perception": self.runtime.perception.health(),
            "runtime_profile": {
                "deployment_profile": self.runtime.config.deployment_profile,
                "runtime_role": self.runtime.config.runtime_role,
                "node_id": self.runtime.config.node_id,
                "core_url": self.runtime.config.core_url,
                "model_loopback_endpoint": self.runtime.config.model_loopback_endpoint,
                "voice_input_adapter": self.runtime.config.voice_input_adapter,
                "voice_output_adapter": self.runtime.config.voice_output_adapter,
            },
            "node_transport": self.runtime.satellite_transport.public_health(),
        }

    async def satellite_connect(self, principal: DemoPrincipal, values: dict[str, object]) -> dict[str, Any]:
        capabilities = values.get("capabilities", ())
        if not isinstance(capabilities, (list, tuple)):
            raise ValueError("satellite capabilities must be a list")
        hello = SatelliteHello(
            str(values.get("device_id", "")),
            str(values.get("owner_id", principal.identity.owner_id)),
            str(values.get("platform", "windows")),
            str(values.get("software_version", "unknown")),
            frozenset(str(item) for item in capabilities if str(item).strip()),
            str(values.get("protocol_version", "1")),
        )
        welcome = await self.runtime.satellite_transport.connect(principal, hello)
        if welcome.accepted:
            await self.runtime.device_fabric.register(
                DeviceRecord(
                    hello.device_id,
                    principal.identity.owner_id,
                    str(values.get("name", hello.device_id)),
                    DeviceRole.PRIMARY_PC.value,
                    "http-long-poll",
                    DeviceStatus.ONLINE.value,
                    hello.capabilities,
                    "verified",
                    datetime.now(UTC),
                    metadata={"protocol": f"jarvis-satellite-v{hello.protocol_version}", "session_id": welcome.session_id},
                )
            )
            await self.runtime.world_state.set_fact(
                principal.identity.owner_id,
                f"device.{hello.device_id}.online",
                True,
                source="satellite",
                source_reference=welcome.session_id,
                freshness_seconds=self.runtime.config.heartbeat_interval_seconds * 3,
                device_id=hello.device_id,
            )
        return asdict(welcome)

    async def satellite_heartbeat(self, principal: DemoPrincipal, values: dict[str, object]) -> dict[str, object]:
        session_id = str(values.get("session_id", ""))
        heartbeat = SatelliteHeartbeat(
            session_id,
            principal.device.device_id,
            int(values.get("sequence", 0)),
        )
        accepted = await self.runtime.satellite_transport.heartbeat(
            principal.identity.owner_id,
            principal.device.device_id,
            heartbeat,
        )
        if not accepted:
            return {"accepted": False, "reason": "satellite_session_invalid"}
        current = await self.runtime.device_fabric.get(
            principal.identity.owner_id,
            principal.device.device_id,
        )
        was_online = current is not None and current.status == DeviceStatus.ONLINE.value
        await self.runtime.device_fabric.heartbeat(
            DeviceHeartbeat(principal.device.device_id, heartbeat.timestamp, {"transport": "http-long-poll", "session_id": session_id}),
            principal.identity.owner_id,
        )
        if not was_online:
            await self.runtime.world_state.set_fact(
                principal.identity.owner_id,
                f"device.{principal.device.device_id}.online",
                True,
                source="satellite",
                source_reference=session_id,
                freshness_seconds=self.runtime.config.heartbeat_interval_seconds * 3,
                device_id=principal.device.device_id,
            )
        return {"accepted": True, "session_id": session_id, "sequence": heartbeat.sequence}

    async def satellite_poll(self, principal: DemoPrincipal, session_id: str, wait_seconds: float) -> dict[str, Any]:
        command = await self.runtime.satellite_transport.poll(
            principal.identity.owner_id,
            principal.device.device_id,
            session_id,
            wait_seconds,
        )
        return {"command": asdict(command) if command else None}

    async def satellite_result(self, principal: DemoPrincipal, values: dict[str, object]) -> dict[str, Any]:
        output = values.get("output", {})
        if not isinstance(output, dict):
            raise ValueError("satellite result output must be an object")
        submission = await self.runtime.satellite_transport.submit_result(
            principal.identity.owner_id,
            principal.device.device_id,
            str(values.get("session_id", "")),
            CommandObservation(
                str(values.get("command_id", "")),
                str(values.get("status", "")),
                output,
                str(values["error_code"]) if values.get("error_code") is not None else None,
            ),
        )
        return asdict(submission)

    async def satellite_disconnect(self, principal: DemoPrincipal, session_id: str) -> dict[str, object]:
        disconnected = await self.runtime.satellite_transport.disconnect(
            principal.identity.owner_id,
            principal.device.device_id,
            session_id,
        )
        if disconnected:
            await self.runtime.device_fabric.mark_offline(
                principal.identity.owner_id,
                principal.device.device_id,
                reason="satellite_disconnected",
            )
            await self.runtime.world_state.set_fact(
                principal.identity.owner_id,
                f"device.{principal.device.device_id}.online",
                False,
                source="satellite",
                source_reference=session_id,
                freshness_seconds=self.runtime.config.heartbeat_interval_seconds * 3,
                device_id=principal.device.device_id,
            )
        return {"accepted": disconnected, "session_id": session_id}

    # Core application use cases ----------------------------------------
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

    # Bounded intelligence use cases -----------------------------------
    async def list_missions(self, owner_id: str) -> list[dict[str, Any]]:
        return [asdict(item) for item in await self.runtime.missions.list(owner_id)]

    async def get_mission(self, owner_id: str, mission_id: str) -> dict[str, Any] | None:
        item = await self.runtime.missions.get(owner_id, mission_id)
        return asdict(item) if item else None

    async def mission_evidence(self, owner_id: str, mission_id: str) -> list[dict[str, Any]]:
        item = await self.runtime.missions.get(owner_id, mission_id)
        if item is None:
            raise KeyError(mission_id)
        return [asdict(evidence) for evidence in item.evidence]

    async def create_mission(self, owner_id: str, values: dict[str, object]) -> dict[str, Any]:
        budget_values = values.get("budget", {})
        budget = MissionBudget(**{key: int(value) if key != "max_duration" else float(value) for key, value in budget_values.items() if key in {"max_steps", "max_duration", "max_tool_calls", "max_worker_runs", "max_replans", "max_external_actions"}}) if isinstance(budget_values, dict) else MissionBudget()
        title = str(values.get("title") or values.get("request") or "").strip()
        request = str(values.get("request") or title).strip()
        item = await self.runtime.missions.create(Mission(str(values.get("mission_id", "")), owner_id, request, title, MissionStatus.DRAFT, values.get("goal_id") if isinstance(values.get("goal_id"), str) else None, budget=budget))
        if bool(values.get("plan", True)):
            item = await self.runtime.missions.plan(owner_id, item.mission_id)
        return asdict(item)

    async def mission_action(self, owner_id: str, mission_id: str, action: str, identity: Identity | None = None, device: DeviceIdentity | None = None, *, approval_granted: bool = False) -> dict[str, Any]:
        if action == "start": item = await self.runtime.missions.start(owner_id, mission_id, identity, device)
        elif action == "pause": item = await self.runtime.missions.pause(owner_id, mission_id)
        elif action == "resume": item = await self.runtime.missions.resume(owner_id, mission_id, approval_granted=approval_granted)
        elif action == "cancel": item = await self.runtime.missions.cancel(owner_id, mission_id)
        else: raise ValueError("unsupported mission action")
        return asdict(item)

    def list_skills(self, *, include_disabled: bool = True) -> list[dict[str, Any]]:
        return [asdict(item) for item in self.runtime.skills.list(include_disabled=include_disabled)]

    def get_skill(self, skill_id: str, *, include_disabled: bool = True) -> dict[str, Any] | None:
        item = self.runtime.skills.get(skill_id, include_disabled=include_disabled)
        return asdict(item) if item else None

    def skill_versions(self, skill_id: str) -> list[dict[str, Any]]:
        return [asdict(item) for item in self.runtime.skills.versions(skill_id)]

    async def set_skill_enabled(self, skill_id: str, enabled: bool) -> dict[str, Any]:
        return asdict(self.runtime.skills.set_enabled(skill_id, enabled).manifest)

    async def execute_skill(self, skill_id: str, values: dict[str, object], identity: Identity, device: DeviceIdentity) -> dict[str, Any]:
        return asdict(await self.runtime.skill_executor.execute(skill_id, values, identity, device))

    async def resume_skill(self, execution_id: str, identity: Identity, device: DeviceIdentity) -> dict[str, Any]:
        return asdict(await self.runtime.skill_executor.resume(execution_id, identity, device))

    async def workspace_projects(self, owner_id: str) -> list[dict[str, Any]]:
        return [asdict(item) for item in await self.runtime.workspace_intelligence.list(owner_id)]

    async def workspace_register(self, owner_id: str, path: str, project_id: str | None = None) -> dict[str, Any]:
        return asdict(await self.runtime.workspace_intelligence.register(owner_id, path, project_id=project_id))

    async def workspace_inspect(self, owner_id: str, project_id: str) -> dict[str, Any]:
        return asdict(await self.runtime.workspace_intelligence.inspect(owner_id, project_id))

    async def intelligence_findings(self, owner_id: str, active_only: bool = False) -> list[dict[str, Any]]:
        return [asdict(item) for item in await self.runtime.event_intelligence.list(owner_id, active_only=active_only)]

    async def detect_intelligence(self, owner_id: str) -> list[dict[str, Any]]:
        return [asdict(item) for item in await self.runtime.event_intelligence.detect(owner_id)]

    async def resolve_intelligence(self, owner_id: str, finding_id: str) -> dict[str, Any]:
        return asdict(await self.runtime.event_intelligence.resolve(owner_id, finding_id))

    async def list_briefings(self, owner_id: str, briefing_type: str | None = None) -> list[dict[str, Any]]:
        return [asdict(item) for item in await self.runtime.briefings.list(owner_id, briefing_type)]

    async def generate_briefing(self, owner_id: str, briefing_type: str = "morning") -> dict[str, Any] | None:
        item = await self.runtime.briefings.generate(owner_id, briefing_type)
        return asdict(item) if item else None

    async def list_automations(self, owner_id: str) -> list[dict[str, Any]]:
        return [asdict(item) for item in await self.runtime.automation.list(owner_id)]

    async def create_automation(self, owner_id: str, values: dict[str, object], identity: Identity | None = None, device: DeviceIdentity | None = None) -> dict[str, Any]:
        trigger_values = values.get("trigger", {})
        trigger = AutomationTrigger(str(trigger_values.get("kind", "event")), str(trigger_values.get("value", ""))) if isinstance(trigger_values, dict) else AutomationTrigger("event", "")
        conditions = tuple(AutomationCondition(str(item.get("key")), str(item.get("operator", "equals")), item.get("value", True)) for item in values.get("conditions", ()) if isinstance(item, dict))
        actions = tuple(AutomationAction(str(item.get("kind")), str(item.get("target")), item.get("arguments", {})) for item in values.get("actions", ()) if isinstance(item, dict))
        item = await self.runtime.automation.create(AutomationRule(str(values.get("rule_id", "")), owner_id, str(values.get("name", "")), trigger, conditions, actions, str(values.get("risk_level", "safe")), float(values.get("cooldown_seconds", 300)), bool(values.get("enabled", True))), identity, device)
        return asdict(item)

    async def set_automation_enabled(self, owner_id: str, rule_id: str, enabled: bool) -> dict[str, Any]:
        return asdict(await self.runtime.automation.set_enabled(owner_id, rule_id, enabled))

    async def list_evaluations(self, owner_id: str | None = None) -> list[dict[str, Any]]:
        return self.runtime.evaluations.list(owner_id)

    async def run_evaluation(self, suite: str, owner_id: str | None = None) -> dict[str, Any]:
        return asdict(await self.runtime.evaluations.run(suite, owner_id=owner_id))

    # Experience and specialist use cases ------------------------------
    async def experience_state(self, owner_id: str) -> dict[str, Any]:
        return await self.runtime.experience.state(owner_id)

    async def experience_system(self, owner_id: str) -> dict[str, Any]:
        system = await self.runtime.experience.system(owner_id)
        result = asdict(system)
        result["observability"] = self.runtime.observability.snapshot()
        return result

    def experience_timeline(self, owner_id: str, limit: int = 100) -> list[dict[str, object]]:
        return self.runtime.experience.timeline(owner_id, limit)

    def experience_hud(self) -> str:
        return self.runtime.experience.hud()

    async def connect_client(self, identity: Identity, device: DeviceIdentity | None, values: dict[str, object]) -> dict[str, Any]:
        topics = tuple(item for item in values.get("subscriptions", ()) if isinstance(item, str))
        return asdict(await self.runtime.clients.connect(identity, device, topics, ui_profile=str(values.get("ui_profile", "hud"))))

    async def disconnect_client(self, identity: Identity, client_session_id: str) -> None:
        await self.runtime.clients.disconnect(client_session_id, identity)

    def list_clients(self, owner_id: str) -> list[dict[str, Any]]:
        return [asdict(item) for item in self.runtime.clients.list(owner_id)]

    def engineering_providers(self) -> list[dict[str, object]]:
        return list(self.runtime.engineering.list_providers())

    async def engineering_session(self, identity: Identity, device: DeviceIdentity, values: dict[str, object]) -> dict[str, Any]:
        root = str(values.get("root", "")).strip()
        if not root:
            raise ValueError("engineering workspace root is required")
        workspace = EngineeringWorkspace(
            str(values.get("workspace_id", "")), root,
            tuple(item for item in values.get("read_scope", (root,)) if isinstance(item, str)),
            tuple(item for item in values.get("write_scope", ()) if isinstance(item, str)),
            frozenset(item for item in values.get("allowed_tools", ()) if isinstance(item, str)),
            float(values.get("timeout_seconds", 30)), str(values.get("risk", "read")), bool(values.get("approval_required", True)),
        )
        session = await self.runtime.engineering.create_session(identity, device, str(values.get("provider", "jupyter")), workspace)
        return asdict(session)

    async def engineering_action(self, identity: Identity, device: DeviceIdentity, values: dict[str, object]) -> dict[str, Any]:
        action = EngineeringAction(str(values["session_id"]), str(values["action"]), values.get("target") if isinstance(values.get("target"), str) else None, values.get("parameters") if isinstance(values.get("parameters"), dict) else {}, bool(values.get("dry_run", True)), values.get("action_id") if isinstance(values.get("action_id"), str) else None)
        return asdict(await self.runtime.engineering.execute(action, identity, device))

    async def engineering_approval(self, identity: Identity, approval_id: str, approved: bool, decided_by: str) -> dict[str, Any]:
        result = await self.runtime.engineering.decide(approval_id, approved, decided_by)
        return asdict(result)

    def engineering_get_session(self, owner_id: str, session_id: str) -> dict[str, Any] | None:
        session = self.runtime.engineering.get_session(session_id, owner_id)
        return asdict(session) if session else None

    async def research_start(self, identity: Identity, device: DeviceIdentity, values: dict[str, object]) -> dict[str, Any]:
        request = ResearchRequest(str(values.get("query", "")), identity.owner_id, device.device_id, int(values.get("max_steps", 8)), int(values.get("max_sources", 8)), float(values.get("max_seconds", 30)), values.get("context") if isinstance(values.get("context"), dict) else {})
        return asdict(await self.runtime.research.start(request, identity, device))

    def research_list(self, owner_id: str) -> list[dict[str, Any]]:
        return [asdict(item) for item in self.runtime.research.list(owner_id)]

    def research_get(self, owner_id: str, run_id: str) -> dict[str, Any] | None:
        run = self.runtime.research.get(run_id, owner_id)
        return asdict(run) if run else None

    async def research_cancel(self, owner_id: str, run_id: str) -> dict[str, Any] | None:
        run = await self.runtime.research.cancel(run_id, owner_id)
        return asdict(run) if run else None

    def research_evidence(self, owner_id: str, run_id: str) -> list[dict[str, Any]]:
        return [asdict(item) for item in self.runtime.research.evidence(run_id, owner_id)]

    async def perception_screen(self, identity: Identity, device: DeviceIdentity, values: dict[str, object]) -> dict[str, Any]:
        if "window_ref" in values and values["window_ref"] is not None and not isinstance(values["window_ref"], str):
            return {"status": "denied", "error_code": "window_ref_required"}
        region_value = values.get("region")
        if region_value is not None and (not isinstance(region_value, dict) or not all(key in region_value for key in ("x", "y", "width", "height"))):
            return {"status": "denied", "error_code": "perception_region_invalid"}
        try:
            region = VisualRegion(*(int(region_value[key]) for key in ("x", "y", "width", "height"))) if isinstance(region_value, dict) else None
        except (TypeError, ValueError, KeyError):
            return {"status": "denied", "error_code": "perception_region_invalid"}
        target = await self.runtime.perception.resolve_target(identity, device, values.get("target_device_id"))
        if target is None:
            return {"status": "denied", "error_code": "target_device_missing"}
        result = await self.runtime.perception.observe_screen(
            identity, device, target_device=target,
            window_ref=values.get("window_ref") if isinstance(values.get("window_ref"), str) else None,
            region=region, mode=str(values.get("mode", "screen")), session_id=str(values.get("session_id", "perception")),
        )
        return asdict(result)

    async def perception_context(self, identity: Identity, device: DeviceIdentity, values: dict[str, object] | None = None) -> dict[str, Any]:
        values = values or {}
        target = await self.runtime.perception.resolve_target(identity, device, values.get("target_device_id"))
        if target is None:
            return {"status": "denied", "error_code": "target_device_missing"}
        return asdict(await self.runtime.perception.observe_desktop_context(identity, device, target_device=target, session_id=str(values.get("session_id", "perception"))))

    async def perception_latest(self, identity: Identity, device: DeviceIdentity, values: dict[str, object] | None = None) -> dict[str, Any]:
        values = values or {}
        target = await self.runtime.perception.resolve_target(identity, device, values.get("target_device_id"))
        if target is None:
            return {"status": "denied", "error_code": "target_device_missing"}
        return asdict(await self.runtime.perception.latest_observation(
            identity,
            device,
            target_device=target,
            observation_id=values.get("observation_id") if isinstance(values.get("observation_id"), str) else None,
            session_id=str(values.get("session_id", "perception")),
        ))

    async def perception_window(self, identity: Identity, device: DeviceIdentity, window: str) -> dict[str, Any]:
        return asdict(await self.runtime.perception.capture_window(identity, device, window))

    def perception_capabilities(self) -> dict[str, object]:
        return self.runtime.perception.capabilities()

    def developer_providers(self) -> list[dict[str, Any]]:
        return [asdict(item) for item in self.runtime.developer_workers.providers()]

    # Computer, browser, device, home, communications, and UI use cases
    async def list_devices(self, owner_id: str) -> list[dict[str, Any]]:
        return [self._device_dict(item) for item in await self.runtime.device_fabric.list(owner_id)]

    async def get_device(self, owner_id: str, device_id: str) -> dict[str, Any] | None:
        device = await self.runtime.device_fabric.get(owner_id, device_id)
        return self._device_dict(device) if device else None

    async def device_capabilities(self, owner_id: str, device_id: str) -> dict[str, Any]:
        return {"device_id": device_id, "capabilities": list(await self.runtime.device_fabric.capabilities(owner_id, device_id))}

    async def computer_action(
        self,
        identity: Identity,
        device: DeviceIdentity,
        action: str,
        parameters: dict[str, object] | None = None,
        *,
        dry_run: bool = True,
        target_device_id: str | None = None,
    ) -> dict[str, Any]:
        target = device
        execution_adapter: str | None = None
        if target_device_id is not None:
            target = await self.runtime.identity.device(target_device_id)
            if target is None:
                return {"status": "denied", "output": {}, "error_code": "target_not_found", "verified": False, "approval_id": None}
            if target.owner_id != identity.owner_id:
                return {"status": "denied", "output": {}, "error_code": "target_owner_mismatch", "verified": False, "approval_id": None}
            target_record = await self.runtime.device_fabric.get(identity.owner_id, target_device_id)
            target_row = self.runtime.repository.device(target_device_id)
            if (target_row is not None and target_row.get("status") != "active") or (target_record is not None and target_record.status == DeviceStatus.REVOKED.value):
                return {"status": "denied", "output": {}, "error_code": "device_revoked", "verified": False, "approval_id": None}
            execution_adapter = "satellite" if (
                target_record is not None and target_record.transport == "http-long-poll"
            ) or self.runtime.satellite.status(target_device_id) != "unknown" else "local"
        result = await self.runtime.computer_actions.execute(
            ComputerAction(action, parameters or {}, dry_run),
            identity,
            device,
            target_device=target,
            execution_adapter=execution_adapter,
        )
        return asdict(result)

    async def decide_computer_action(
        self,
        approval_id: str,
        approved: bool,
        decided_by: str,
        identity: Identity | None = None,
        device: DeviceIdentity | None = None,
    ) -> dict[str, Any]:
        if self.runtime.repository.tool_call_by_approval(approval_id) is not None:
            return asdict(ComputerResult("denied", error_code="delegated_approval_requires_run_resume", approval_id=approval_id))
        return asdict(await self.runtime.computer_actions.decide(approval_id, approved, decided_by, identity=identity, device=device))

    async def browser_action(
        self,
        identity: Identity,
        device: DeviceIdentity,
        action: str,
        parameters: dict[str, object] | None = None,
        *,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        result = await self.runtime.browser_actions.execute(
            BrowserAction(action, parameters or {}, dry_run), identity, device
        )
        return asdict(result)

    async def decide_browser_action(self, approval_id: str, approved: bool, decided_by: str) -> dict[str, Any]:
        return asdict(await self.runtime.browser_actions.decide(approval_id, approved, decided_by))

    async def home_entities(self, identity: Identity, device: DeviceIdentity) -> list[dict[str, Any]]:
        return [asdict(item) for item in await self.runtime.home.list_entities(identity, device)]

    async def home_action(
        self,
        identity: Identity,
        device: DeviceIdentity,
        entity_id: str,
        action: str,
        parameters: dict[str, object] | None = None,
        *,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        result = await self.runtime.home.execute(
            HomeAction(entity_id, action, parameters or {}, dry_run), identity, device
        )
        return asdict(result)

    async def communication_channels(self) -> list[dict[str, Any]]:
        return [{"name": name, "available": True, "local": name == "local"} for name in self.runtime.communications.list_channels()]

    async def communication_messages(self, owner_id: str, *, channel: str | None = None, query: str | None = None) -> list[dict[str, Any]]:
        channels = (channel,) if channel else self.runtime.communications.list_channels()
        for name in channels:
            if name in self.runtime.communications.channels:
                await self.runtime.communications.sync(owner_id, name)
        return [asdict(item) for item in await self.runtime.communications.list_messages(owner_id, channel, query)]

    async def communication_draft(self, owner_id: str, channel: str, recipient: str, content: str, reply_to: str | None = None) -> dict[str, Any]:
        return asdict(await self.runtime.communications.draft(owner_id, channel, recipient, content, reply_to))

    async def communication_send(
        self,
        identity: Identity,
        device: DeviceIdentity,
        channel: str,
        recipient: str,
        content: str,
        *,
        important: bool = False,
    ) -> dict[str, Any]:
        return asdict(await self.runtime.communications.send(identity.owner_id, channel, recipient, content, identity, device, important=important))

    async def communication_intelligence(self, owner_id: str, thread_id: str, message_ids: tuple[str, ...] = ()) -> dict[str, Any]:
        messages = await self.runtime.communications.list_messages(owner_id)
        selected = tuple(item for item in messages if not message_ids or item.message_id in message_ids)
        insight = await self.runtime.communications_intelligence.analyze(owner_id, thread_id, selected)
        return asdict(insight)

    async def get_communication_intelligence(self, owner_id: str, thread_id: str) -> dict[str, Any] | None:
        insight = await self.runtime.communications_intelligence.get(owner_id, thread_id)
        return asdict(insight) if insight else None

    async def decide_communication_send(self, owner_id: str, approval_id: str, approved: bool, decided_by: str) -> dict[str, Any]:
        return asdict(await self.runtime.communications.decide_send(owner_id, approval_id, approved, decided_by))

    async def list_notifications(self, owner_id: str, active_only: bool = False) -> list[dict[str, Any]]:
        return [asdict(item) for item in await self.runtime.notifications.list(owner_id, active_only)]

    async def presence(self, owner_id: str) -> dict[str, Any]:
        return asdict(await self.runtime.presence.refresh(owner_id))

    async def attention(self, owner_id: str) -> dict[str, Any]:
        mode = await self.runtime.operations.mode(owner_id)
        presence = await self.runtime.presence.refresh(owner_id)
        focus = await self.runtime.operations.focus(owner_id)
        return {"mode": mode.mode, "presence": asdict(presence), "voice_active": self.runtime.voice.state.value in {"listening", "thinking", "speaking", "follow_up"}, "focus": asdict(focus) if focus else None}

    async def personal_modes(self, owner_id: str) -> list[dict[str, Any]]:
        return [asdict(item) for item in await self.runtime.operations.modes(owner_id)]

    async def set_personal_mode(self, owner_id: str, mode: str, *, ttl_seconds: float | None = None, source: str = "user") -> dict[str, Any]:
        return asdict(await self.runtime.operations.set_mode(owner_id, mode, ttl_seconds=ttl_seconds, source=source))

    async def personal_operation(self, owner_id: str, operation: str, values: dict[str, object] | None = None, *, identity: Identity | None = None, device: DeviceIdentity | None = None) -> dict[str, Any]:
        return asdict(await self.runtime.operations.run(owner_id, operation, identity=identity, device=device, values=values))

    async def focus_state(self, owner_id: str) -> dict[str, Any]:
        focus = await self.runtime.operations.focus(owner_id)
        return asdict(focus) if focus else {"owner_id": owner_id, "status": "inactive"}

    async def focus_start(self, owner_id: str, values: dict[str, object]) -> dict[str, Any]:
        duration = values.get("duration_seconds")
        return asdict(await self.runtime.operations.start_focus(owner_id, duration_seconds=float(duration) if duration is not None else None, goal_id=values.get("goal_id") if isinstance(values.get("goal_id"), str) else None, mission_id=values.get("mission_id") if isinstance(values.get("mission_id"), str) else None))

    async def focus_end(self, owner_id: str, values: dict[str, object] | None = None) -> dict[str, Any]:
        values = values or {}
        return asdict(await self.runtime.operations.end_focus(owner_id, reason=values.get("reason") if isinstance(values.get("reason"), str) else None))

    async def communication_followups(self, owner_id: str, active_only: bool = False) -> list[dict[str, Any]]:
        return [asdict(item) for item in await self.runtime.communication_followups.list(owner_id, active_only=active_only)]

    async def acknowledge_communication_followup(self, owner_id: str, followup_id: str) -> dict[str, Any]:
        return asdict(await self.runtime.communication_followups.acknowledge(owner_id, followup_id))

    async def create_communication_followup(self, owner_id: str, values: dict[str, object]) -> dict[str, Any]:
        return asdict(await self.runtime.communication_followups.create(owner_id, str(values["thread_id"]), message_id=values.get("message_id") if isinstance(values.get("message_id"), str) else None, direction=str(values.get("direction", "awaiting_other_party")), summary=str(values.get("summary", "Awaiting reply")), due_at=self._parse_datetime(values.get("due_at")), delay_seconds=float(values.get("delay_seconds", 86400)), related_goal_id=values.get("related_goal_id") if isinstance(values.get("related_goal_id"), str) else None, related_mission_id=values.get("related_mission_id") if isinstance(values.get("related_mission_id"), str) else None, metadata=values.get("metadata") if isinstance(values.get("metadata"), dict) else None))

    async def communication_auto_send_rules(self, owner_id: str) -> list[dict[str, Any]]:
        return [asdict(item) for item in await self.runtime.communication_followups.rules(owner_id)]

    async def create_communication_auto_send_rule(self, owner_id: str, values: dict[str, object]) -> dict[str, Any]:
        return asdict(await self.runtime.communication_followups.create_rule(owner_id, values))

    async def update_communication_auto_send_rule(self, owner_id: str, rule_id: str, values: dict[str, object]) -> dict[str, Any]:
        return asdict(await self.runtime.communication_followups.update_rule(owner_id, rule_id, values))

    async def home_context(self, identity: Identity, device: DeviceIdentity) -> dict[str, Any]:
        return asdict(await self.runtime.home_context.refresh(identity, device))

    def routines(self) -> list[dict[str, Any]]:
        return [asdict(item) for item in self.runtime.home_routines.list()]

    async def run_routine(self, routine_id: str, identity: Identity, device: DeviceIdentity, *, dry_run: bool = True) -> dict[str, Any]:
        return asdict(await self.runtime.home_routines.run(routine_id, identity, device, dry_run=dry_run))

    async def create_notification(self, owner_id: str, values: dict[str, object]) -> dict[str, Any]:
        action_options = tuple(item for item in values.get("action_options", ()) if isinstance(item, str))
        expires_at = self._parse_datetime(values.get("expires_at"))
        notification = await self.runtime.notifications.create(
            owner_id,
            str(values.get("title", "")),
            str(values.get("message", "")),
            severity=str(values.get("severity", "info")),
            source=str(values.get("source", "api")),
            action_options=action_options,
            target_device=values.get("target_device") if isinstance(values.get("target_device"), str) else None,
            expires_at=expires_at,
            dedup_key=values.get("dedup_key") if isinstance(values.get("dedup_key"), str) else None,
            metadata=values.get("metadata") if isinstance(values.get("metadata"), dict) else None,
        )
        return asdict(notification)

    async def dismiss_notification(self, owner_id: str, notification_id: str) -> dict[str, Any]:
        return asdict(await self.runtime.notifications.dismiss(owner_id, notification_id))

    async def deliver_notification(self, owner_id: str, notification_id: str, values: dict[str, object] | None = None) -> dict[str, Any]:
        result = await self.runtime.notification_delivery.deliver(owner_id, notification_id)
        return asdict(result)

    def capabilities(self, device_id: str | None = None) -> list[dict[str, Any]]:
        return [asdict(item) for item in self.runtime.capabilities.list(device_id=device_id)]

    @staticmethod
    def _device_dict(device: DeviceRecord) -> dict[str, Any]:
        result = asdict(device)
        result["capabilities"] = sorted(device.capabilities)
        return result

    @staticmethod
    def _parse_datetime(value: object) -> datetime | None:
        if value is None or value == "":
            return None
        if not isinstance(value, str):
            raise ValueError("datetime must be an ISO string")
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    def events(self, correlation_id: str | None = None, owner_id: str | None = None) -> list[dict[str, Any]]:
        return self.runtime.repository.events(correlation_id, owner_id)

    async def approval(self, approval_id: str, owner_id: str | None = None) -> dict[str, Any] | None:
        row = self.runtime.repository.approval(approval_id)
        if row is None or (owner_id is not None and row.get("requester_id") != owner_id):
            return None
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
