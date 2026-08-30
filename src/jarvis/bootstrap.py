"""Dependency composition and lifecycle for the product-owned JARVIS runtime."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import AsyncIterator
from uuid import uuid4
from pathlib import Path

from .bus import InMemoryEventBus
from .config import JarvisConfig
from .authority.audit.service import DurableAuditService
from .authority.approvals.service import DurableApprovalEngine
from .authority.identity.service import IdentityService as RuntimeIdentityService
from .authority.permissions.engine import PolicyPermissionEngine
from .agents.runtime.runtime import AgentRuntime
from .autonomy.policy import AutonomyPolicy
from .capabilities.registry import CapabilityRegistry
from .communications.hub import CommunicationsHub, LocalCommunicationChannel
from .computer.controller import WindowsComputerController
from .computer.service import ComputerActionService, WindowsNativeComputerController
from .context.assembler import ContextAssembler
from .contracts import (
    ApprovalEngine,
    AuditService,
    BrowserController,
    CommunicationChannel,
    ComputerController,
    GoalEngine,
    MemoryService,
    PermissionEngine,
    RealtimeVoiceSession,
    SpeechToText,
    TextToSpeech,
    WorldState,
    CapabilityDescriptor,
    ApprovalProjection,
    DeviceProjection,
    GoalProjection,
    NotificationProjection,
)
from .devices.satellite.registry import WindowsSatelliteRegistry
from .devices.satellite.transport import SatelliteTransportService
from .devices.fabric import DeviceFabricService
from .devices.home.service import HomeActionService, RestrictedMQTTTransport
from .events import Event, EventCategory, EventState
from .models.gateway import ModelGateway
from .models.routing import ModelRoute
from .persistence.db import SQLiteDatabase
from .persistence.backup import SQLiteBackupService
from .persistence.repositories import RuntimeRepository
from .memory.service import DurableMemoryService
from .nodes.venom import VenomNode
from .offline.service import OfflineModeService
from .personalization.service import DurablePersonalizationService
from .proactive.service import DurableProactiveService
from .notifications.service import NotificationService
from .runtime.noop import NoOpSpeechToText, NoOpTextToSpeech
from .scheduler.service import BackgroundScheduler
from .tools.registry import ToolRegistry, default_registry
from .tools.service import ToolExecutionService
from .voice.core import VoiceCore
from .voice.routing.service import VoiceRoutingService
from .browser.service import BrowserActionService, LocalBrowserController
from .world_state.service import DurableWorldStateService
from .world_state.workspace import WorkspaceContextService
from .goals.engine import DurableGoalEngine
from .clients.service import ClientSessionService
from .developer.service import DeveloperWorkerGateway
from .engineering.providers import JupyterEngineeringProvider, KiCadEngineeringProvider
from .engineering.service import EngineeringService, EngineeringWorker
from .experience.gateway import ExperienceGatewayService
from .experience.projections import ExperienceProjection
from .observability.service import ObservabilityService
from .perception.service import PerceptionService
from .research.providers import LocalDocumentProvider
from .research.service import ResearchService
from .missions.service import MissionService
from .skills.registry import SkillRegistry, builtin_skills
from .skills.executor import SkillExecutor
from .skills.policy import SkillPolicy
from .workspace.service import WorkspaceIntelligenceService
from .intelligence.events.service import EventIntelligenceService
from .briefings.service import BriefingService
from .automation.service import AutomationService
from .communications.intelligence.service import CommunicationIntelligenceService
from .communications.intelligence.service import CommunicationFollowUpService
from .agents.workers.coordination import WorkerCoordinator
from .evaluation.service import EvaluationService
from .evaluation.improvement import ControlledImprovementPolicy
from .presence.service import PresenceService
from .attention.policy import AttentionPolicy
from .notifications.delivery import NotificationDeliveryCoordinator
from .operations.service import PersonalOperationsService
from .home.service import HomeContextService, HomeRoutineService


class RuntimeState(StrEnum):
    CREATED = "created"
    STARTING = "starting"
    READY = "ready"
    STOPPING = "stopping"
    STOPPED = "stopped"


@dataclass(slots=True)
class JarvisRuntime:
    """A composed foundation runtime with explicit lifecycle state."""

    config: JarvisConfig
    event_bus: InMemoryEventBus
    database: SQLiteDatabase
    repository: RuntimeRepository
    identity: RuntimeIdentityService
    permission: PermissionEngine
    approval: ApprovalEngine
    audit: AuditService
    models: ModelGateway
    tools: ToolRegistry
    tool_service: ToolExecutionService
    agent: AgentRuntime
    satellite: WindowsSatelliteRegistry
    memory: MemoryService
    world_state: DurableWorldStateService
    goals: GoalEngine
    personalization: DurablePersonalizationService
    proactive: DurableProactiveService
    context: ContextAssembler
    autonomy: AutonomyPolicy
    offline: OfflineModeService
    workspace: WorkspaceContextService
    scheduler: BackgroundScheduler
    venom: VenomNode
    computer: ComputerController
    browser: BrowserController
    voice: RealtimeVoiceSession
    stt: SpeechToText
    tts: TextToSpeech
    communication: CommunicationChannel
    device_fabric: DeviceFabricService
    computer_actions: ComputerActionService
    browser_actions: BrowserActionService
    home: HomeActionService
    communications: CommunicationsHub
    notifications: NotificationService
    voice_routing: VoiceRoutingService
    capabilities: CapabilityRegistry
    experience: ExperienceGatewayService
    experience_projection: ExperienceProjection
    clients: ClientSessionService
    observability: ObservabilityService
    engineering: EngineeringService
    engineering_worker: EngineeringWorker
    research: ResearchService
    perception: PerceptionService
    developer_workers: DeveloperWorkerGateway
    missions: MissionService
    skills: SkillRegistry
    skill_executor: SkillExecutor
    workspace_intelligence: WorkspaceIntelligenceService
    event_intelligence: EventIntelligenceService
    briefings: BriefingService
    automation: AutomationService
    communications_intelligence: CommunicationIntelligenceService
    communication_followups: CommunicationFollowUpService
    presence: PresenceService
    attention: AttentionPolicy
    notification_delivery: NotificationDeliveryCoordinator
    operations: PersonalOperationsService
    home_context: HomeContextService
    home_routines: HomeRoutineService
    worker_coordinator: WorkerCoordinator
    evaluations: EvaluationService
    improvement_policy: ControlledImprovementPolicy
    backup: SQLiteBackupService
    runtime_id: str
    satellite_transport: SatelliteTransportService
    state: RuntimeState = RuntimeState.CREATED

    async def start(self) -> None:
        if self.state is RuntimeState.READY:
            return
        if self.state is not RuntimeState.CREATED:
            raise RuntimeError(f"cannot start runtime from {self.state.value}")
        self.state = RuntimeState.STARTING
        reconciled = self.repository.reconcile_active_runs()
        if reconciled:
            recovery = Event.create(
                "system.runtime.reconciled", EventCategory.SYSTEM,
                correlation_id=self.runtime_id, state=EventState.COMPLETED,
                payload={"reconciled_runs": reconciled},
            )
            self.repository.append_event(recovery)
            await self.event_bus.publish(recovery)
        await self.scheduler.start()
        correlation_id = self.runtime_id
        started = Event.create(
            "system.bootstrap.started",
            EventCategory.SYSTEM,
            correlation_id=correlation_id,
            payload={"service_name": self.config.service_name},
        )
        self.repository.append_event(started)
        await self.event_bus.publish(started)
        self.state = RuntimeState.READY
        ready = Event.create(
            "system.bootstrap.ready",
            EventCategory.SYSTEM,
            correlation_id=correlation_id,
            state=EventState.COMPLETED,
            payload={"environment": self.config.environment},
        )
        self.repository.append_event(ready)
        await self.event_bus.publish(ready)

    async def shutdown(self) -> None:
        if self.state is RuntimeState.STOPPED:
            return
        if self.state is not RuntimeState.READY:
            raise RuntimeError(f"cannot shut down runtime from {self.state.value}")
        self.state = RuntimeState.STOPPING
        await self.scheduler.stop()
        if getattr(self.voice.state, "value", None) != "stopped":
            try:
                await self.voice.stop()
            except RuntimeError:
                pass
        started = Event.create(
            "system.shutdown.started",
            EventCategory.SYSTEM,
            correlation_id=self.runtime_id,
        )
        self.repository.append_event(started)
        await self.event_bus.publish(started)
        completed = Event.create(
            "system.shutdown.completed",
            EventCategory.SYSTEM,
            correlation_id=self.runtime_id,
            state=EventState.COMPLETED,
        )
        self.repository.append_event(completed)
        await self.event_bus.publish(completed)
        self.experience_projection.close()
        self.observability.close()
        self.satellite_transport.close()
        self.state = RuntimeState.STOPPED
        self.database.close()
        await self.event_bus.close()


def create_runtime(config: JarvisConfig | None = None) -> JarvisRuntime:
    """Compose the foundation without opening I/O or loading any model."""

    effective_config = config or JarvisConfig.from_env()
    database_path = ":memory:" if effective_config.environment in {"test", "offline-test"} else effective_config.database_path
    database = SQLiteDatabase(database_path)
    backup_service = SQLiteBackupService(database)
    repository = RuntimeRepository(database)
    event_bus = InMemoryEventBus()
    permission = PolicyPermissionEngine()
    approval = DurableApprovalEngine(repository)
    audit = DurableAuditService(repository)
    registry = default_registry()
    tool_service = ToolExecutionService(repository, event_bus, registry, permission, approval, audit)
    models = ModelGateway(effective_config)
    satellite = WindowsSatelliteRegistry()
    satellite_transport = SatelliteTransportService(
        satellite,
        heartbeat_interval_seconds=effective_config.heartbeat_interval_seconds,
    )
    stt = NoOpSpeechToText()
    tts = NoOpTextToSpeech()
    memory = DurableMemoryService(repository, event_bus, audit)
    world_state = DurableWorldStateService(repository, event_bus)
    goals = DurableGoalEngine(repository, event_bus, audit)
    personalization = DurablePersonalizationService(repository, event_bus, audit)
    autonomy = AutonomyPolicy()
    offline = OfflineModeService()
    proactive = DurableProactiveService(repository, event_bus, world_state, goals, tool_service, audit, autonomy)
    capabilities = CapabilityRegistry()
    device_fabric = DeviceFabricService(repository, event_bus, audit)
    computer_controller = WindowsNativeComputerController()
    computer_actions = ComputerActionService(computer_controller, repository, event_bus, permission, audit, approval)
    browser_controller = LocalBrowserController()
    browser_actions = BrowserActionService(browser_controller, repository, event_bus, permission, audit, approval)
    home = HomeActionService(None, repository, event_bus, permission, audit, RestrictedMQTTTransport())
    communications = CommunicationsHub(repository, event_bus, approval, permission, audit, autonomy)
    local_channel = LocalCommunicationChannel()
    communications.register_channel(local_channel)
    notifications = NotificationService(repository, event_bus, audit)
    voice_routing = VoiceRoutingService(repository, event_bus)
    _register_capabilities(capabilities)
    context = ContextAssembler(memory, world_state, goals, proactive, personalization, registry, offline, capabilities)
    agent = AgentRuntime(repository, event_bus, models, tool_service, max_steps=effective_config.max_agent_steps, context_assembler=context)
    scheduler = BackgroundScheduler()
    runtime_ref: dict[str, JarvisRuntime] = {}
    workspace_context = WorkspaceContextService(world_state)
    missions = MissionService(repository, event_bus, permission=permission, approvals=approval, audit=audit)
    skills = SkillRegistry(repository)
    for builtin in builtin_skills():
        skills.register(builtin)
    skill_executor = SkillExecutor(skills, SkillPolicy(permission, registry), event_bus, repository, tools=tool_service, approvals=approval, audit=audit)
    workspace_intelligence = WorkspaceIntelligenceService(repository, event_bus, workspace_context)
    event_intelligence = EventIntelligenceService(repository, event_bus)
    briefings = BriefingService(repository, event_bus)
    automation = AutomationService(repository, event_bus, skill_executor=skill_executor, missions=missions, briefings=briefings, offline=offline, capabilities=capabilities)
    automation.notifications = notifications
    communications_intelligence = CommunicationIntelligenceService(repository, event_bus)
    communication_followups = CommunicationFollowUpService(repository, event_bus, communications_intelligence, communications, personalization)
    event_bus.subscribe("communication.received", communication_followups.handle_communication_event)
    event_bus.subscribe("communication.sent", communication_followups.handle_communication_event)
    worker_coordinator = WorkerCoordinator(repository, event_bus, developer_gateway=None, permission=permission)
    evaluations = EvaluationService(repository, event_bus)
    evaluations.register_default_suites()
    improvement_policy = ControlledImprovementPolicy()
    clients = ClientSessionService(repository, event_bus)
    presence = PresenceService(world_state, voice_routing, clients, device_fabric, repository, event_bus)
    attention = AttentionPolicy()
    operations = PersonalOperationsService(repository, event_bus, world_state, personalization, goals=goals, missions=missions, briefings=briefings, notifications=notifications, automation=automation, offline=offline)
    voice = VoiceCore(agent, event_bus, stt, tts)
    notification_delivery = NotificationDeliveryCoordinator(notifications, attention, presence, voice_routing, repository, event_bus, personalization=personalization, operations=operations, voice_core=voice)
    async def _attention_queue_trigger(event: Event) -> None:
        owner_id = event.payload.get("owner_id")
        if isinstance(owner_id, str): await notification_delivery.reevaluate_queued(owner_id)
    event_bus.subscribe("focus.ended", _attention_queue_trigger)
    event_bus.subscribe("focus.interrupted", _attention_queue_trigger)
    event_bus.subscribe("attention.mode_changed", _attention_queue_trigger)
    home_context = HomeContextService(home, world_state, repository, event_bus)
    home_routines = HomeRoutineService(home_context, home, repository, event_bus)
    operations.home_routines = home_routines

    async def experience_state(owner_id: str) -> dict[str, object]:
        devices = tuple(
            DeviceProjection(item.device_id, item.status, item.name, tuple(sorted(item.capabilities)), item.last_seen)
            for item in await device_fabric.list(owner_id)
        )
        goals_view = tuple(
            GoalProjection(item.goal_id, item.title or item.description, item.status.value, item.priority)
            for item in await goals.list(owner_id)
        )
        notifications_view = tuple(
            NotificationProjection(item.notification_id, item.title, item.message, item.severity, item.dismissed_at is not None)
            for item in await notifications.list(owner_id)
        )
        approvals_view = tuple(
            ApprovalProjection(str(row["id"]), str(row["action"]), str(row["status"]), row.get("decision_reason"))
            for row in repository.pending_approvals(owner_id)
        )
        missions_view = tuple(asdict(item) for item in await missions.list(owner_id))
        skills_view = tuple(asdict(item) for item in skills.list(include_disabled=True))
        automation_view = tuple(asdict(item) for item in await automation.list(owner_id))
        briefing_view = tuple(asdict(item) for item in await briefings.list(owner_id))
        intelligence_view = tuple(asdict(item) for item in await event_intelligence.list(owner_id, active_only=True))
        workspace_view = tuple(asdict(item) for item in await workspace_intelligence.list(owner_id))
        worker_view = tuple(asdict(item) for item in await worker_coordinator.list(owner_id))
        evaluation_view = tuple(evaluations.list(owner_id))
        presence_view = asdict(await presence.snapshot(owner_id))
        mode_view = asdict(await operations.mode(owner_id))
        focus = await operations.focus(owner_id)
        focus_view = asdict(focus) if focus else None
        followup_view = tuple(asdict(item) for item in await communication_followups.list(owner_id, active_only=True))
        home_view = asdict(await home_context.snapshot(owner_id))
        model = await models.health(ModelRoute.GENERAL_REASONING)
        current = runtime_ref.get("runtime")
        return {
            "system": {
                "runtime_state": current.state.value if current else "created",
                "offline": not offline.state.online,
                "model_provider": model.provider,
                "model_available": model.available,
                "topology": {
                    "profile": effective_config.deployment_profile,
                    "node_id": effective_config.node_id,
                    "core_role": effective_config.runtime_role,
                    "node_transport": satellite_transport.health(),
                },
            },
            "devices": devices,
            "goals": goals_view,
            "notifications": notifications_view,
            "approvals": approvals_view,
            "missions": missions_view,
            "skills": skills_view,
            "automations": automation_view,
            "briefings": briefing_view,
            "intelligence": intelligence_view,
            "workspace": workspace_view,
            "worker_delegations": worker_view,
            "evaluations": evaluation_view,
            "presence": presence_view,
            "attention": {"mode": mode_view["mode"], "focus_active": focus_view is not None},
            "operations": {"mode": mode_view, "recent": [asdict(item) for item in await operations.modes(owner_id)][:5]},
            "focus": focus_view,
            "follow_ups": followup_view,
            "home": home_view,
        }

    experience_projection = ExperienceProjection(event_bus, experience_state, repository=repository)
    observability = ObservabilityService(event_bus)
    engineering = EngineeringService(
        repository, event_bus, permission, approval, audit,
        (JupyterEngineeringProvider(), KiCadEngineeringProvider()),
    )
    engineering_worker = EngineeringWorker(engineering, event_bus, repository)
    research = ResearchService(repository, event_bus, permission, audit, local=LocalDocumentProvider((str(Path.cwd()),)))
    perception = PerceptionService(repository, event_bus, permission, audit)
    developer_workers = DeveloperWorkerGateway()
    worker_coordinator.developer_gateway = developer_workers

    async def skill_system_health(skill: object, values: dict[str, object], identity: object, device: object) -> dict[str, object]:
        del skill, values, identity, device
        health = await models.health(ModelRoute.GENERAL_REASONING)
        current = runtime_ref.get("runtime")
        return {"runtime_state": current.state.value if current else "created", "model_provider": health.provider, "model_available": health.available, "offline": not offline.state.online}

    async def skill_project_status(skill: object, values: dict[str, object], identity: object, device: object) -> dict[str, object]:
        del skill, device
        project_id = values.get("project_id")
        if isinstance(project_id, str):
            item = await workspace_intelligence.get(identity.owner_id, project_id)
            return {"project": asdict(item) if item else None}
        return {"projects": [asdict(item) for item in await workspace_intelligence.list(identity.owner_id)]}

    async def skill_briefing(skill: object, values: dict[str, object], identity: object, device: object) -> dict[str, object]:
        del skill, device
        item = await briefings.generate(identity.owner_id, str(values.get("briefing_type", "morning")))
        return {"briefing": asdict(item) if item else None}

    async def skill_research(skill: object, values: dict[str, object], identity: object, device: object) -> dict[str, object]:
        del skill
        request = ResearchRequest(str(values.get("query", "")), identity.owner_id, device.device_id, 8, 8, 30.0, {})
        return asdict(await research.start(request, identity, device))

    def skill_backup(skill: object, values: dict[str, object], identity: object, device: object) -> dict[str, object]:
        del skill, identity, device
        destination = str(values.get("destination", "")).strip()
        if not destination:
            raise ValueError("backup destination is required")
        target = Path(destination).expanduser().resolve(strict=False)
        roots = [Path.cwd().resolve()]
        if database.path != ":memory:":
            roots.append(Path(database.path).expanduser().resolve(strict=False).parent)
        if not any(target == root or root in target.parents for root in roots):
            raise PermissionError("backup_destination_out_of_scope")
        return backup_service.create(destination)

    skill_executor.handlers.update({"system.health": skill_system_health, "workspace.project_status": skill_project_status, "briefing.generate": skill_briefing, "research.start": skill_research, "backup.create": skill_backup})
    for provider in developer_workers.providers():
        capabilities.register(CapabilityDescriptor(
            f"developer.{provider.name}", "developer-worker-gateway", None, provider.available, "bounded",
            permission="tool.request", metadata={"executable": provider.executable, "reason": provider.reason},
        ))

    async def maintenance_owner() -> str | None:
        owner = repository.first_owner()
        return str(owner["id"]) if owner else None

    async def maintain_memory() -> dict[str, int]:
        owner_id = await maintenance_owner()
        return await memory.maintain(owner_id) if owner_id else {"expired": 0, "archived": 0}

    async def expire_world_state() -> int:
        owner_id = await maintenance_owner()
        return await world_state.expire(owner_id) if owner_id else 0

    async def expire_presence() -> int:
        owner_id = await maintenance_owner()
        return await presence.expire(owner_id) if owner_id else 0

    async def detect_followups() -> int:
        owner_id = await maintenance_owner()
        return len(await communication_followups.due(owner_id)) if owner_id else 0

    async def reevaluate_notification_queue() -> int:
        owner_id = await maintenance_owner()
        return len(await notification_delivery.reevaluate_queued(owner_id)) if owner_id else 0
    async def retain_phase08() -> dict[str, int]:
        owner_id = await maintenance_owner()
        return repository.cleanup_phase08_operational_state(owner_id, now=datetime.now(UTC)) if owner_id else {}

    async def detect_proactive() -> int:
        owner_id = await maintenance_owner()
        return len(await proactive.detect(owner_id)) if owner_id else 0

    async def detect_event_intelligence() -> int:
        owner_id = await maintenance_owner()
        return len(await event_intelligence.detect(owner_id)) if owner_id else 0

    async def run_automation_tick() -> int:
        owner_id = await maintenance_owner()
        return len(await automation.run_schedule(owner_id)) if owner_id else 0

    async def refresh_satellite_health() -> int:
        owner_id = await maintenance_owner()
        if not owner_id:
            return 0
        changed = await device_fabric.mark_stale_offline(
            owner_id,
            max_age_seconds=max(30, int(effective_config.heartbeat_interval_seconds * 3)),
        )
        return len(changed)

    async def refresh_health() -> dict[str, object]:
        await offline.refresh()
        model_health = await models.health(ModelRoute.GENERAL_REASONING)
        return {"model": model_health.provider, "offline": offline.state.online}

    scheduler.add("memory-maintenance", 300, maintain_memory)
    scheduler.add("world-state-expiry", 60, expire_world_state)
    scheduler.add("presence-expiry", 60, expire_presence)
    scheduler.add("communication-followups", 60, detect_followups)
    scheduler.add("notification-queue-check", 60, reevaluate_notification_queue)
    scheduler.add("phase08-operational-retention", 21600, retain_phase08)
    scheduler.add("goal-proactive-check", 60, detect_proactive)
    scheduler.add("event-intelligence-check", 60, detect_event_intelligence)
    scheduler.add("automation-check", 60, run_automation_tick)
    scheduler.add("satellite-health", 60, refresh_satellite_health)
    scheduler.add("health-check", 120, refresh_health)
    runtime = JarvisRuntime(
        config=effective_config,
        event_bus=event_bus,
        database=database,
        repository=repository,
        identity=RuntimeIdentityService(repository),
        permission=permission,
        approval=approval,
        audit=audit,
        models=models,
        tools=registry,
        tool_service=tool_service,
        agent=agent,
        satellite=satellite,
        memory=memory,
        world_state=world_state,
        goals=goals,
        personalization=personalization,
        proactive=proactive,
        context=context,
        autonomy=autonomy,
        offline=offline,
        workspace=workspace_context,
        scheduler=scheduler,
        venom=VenomNode(),
        computer=WindowsComputerController(satellite),
        browser=browser_controller,
        voice=voice,
        stt=stt,
        tts=tts,
        communication=local_channel,
        device_fabric=device_fabric,
        computer_actions=computer_actions,
        browser_actions=browser_actions,
        home=home,
        communications=communications,
        notifications=notifications,
        voice_routing=voice_routing,
        capabilities=capabilities,
        experience=ExperienceGatewayService(experience_projection),
        experience_projection=experience_projection,
        clients=clients,
        observability=observability,
        engineering=engineering,
        engineering_worker=engineering_worker,
        research=research,
        perception=perception,
        developer_workers=developer_workers,
        missions=missions,
        skills=skills,
        skill_executor=skill_executor,
        workspace_intelligence=workspace_intelligence,
        event_intelligence=event_intelligence,
        briefings=briefings,
        automation=automation,
        communications_intelligence=communications_intelligence,
        communication_followups=communication_followups,
        presence=presence,
        attention=attention,
        notification_delivery=notification_delivery,
        operations=operations,
        home_context=home_context,
        home_routines=home_routines,
        worker_coordinator=worker_coordinator,
        evaluations=evaluations,
        improvement_policy=improvement_policy,
        backup=backup_service,
        runtime_id=f"runtime-{uuid4()}",
        satellite_transport=satellite_transport,
    )
    runtime_ref["runtime"] = runtime
    return runtime


def _register_capabilities(capabilities: CapabilityRegistry) -> None:
    """Register only deterministic local or explicitly available seams."""
    from platform import system

    windows = system().casefold() == "windows"
    computer = (
        "computer.open_application", "computer.open_file", "computer.open_folder",
        "computer.list_processes", "computer.inspect_file", "computer.search_files",
        "computer.stop_safe_process",
    )
    for capability in computer:
        capabilities.register(CapabilityDescriptor(capability, "windows-native", None, windows, "safe"))
    for capability in ("browser.open_url", "browser.navigate", "browser.read_page", "browser.extract_text", "browser.find_element", "browser.inspect_accessibility_tree", "browser.tabs"):
        capabilities.register(CapabilityDescriptor(capability, "local-browser", None, True, "read", requires_internet=capability != "browser.tabs"))
    capabilities.register(CapabilityDescriptor("communication.local.draft", "local-channel", None, True, "safe"))
    capabilities.register(CapabilityDescriptor("notification.create", "local-notification", None, True, "safe"))
    capabilities.register(CapabilityDescriptor("backup.create", "sqlite-backup", None, True, "safe", permission="tool.request"))
    capabilities.register(CapabilityDescriptor(
        "device.venom.health", "venom", "venom", False, "read",
        metadata={"reason": "not_probed", "network": "unknown-until-deployment"},
    ))
    capabilities.register(CapabilityDescriptor("engineering.jupyter", "jupyter-adapter", None, False, "read", permission="tool.request", metadata={"reason": "adapter_injected_at_deployment"}))
    capabilities.register(CapabilityDescriptor("engineering.kicad", "kicad-adapter", None, False, "read", permission="tool.request", metadata={"reason": "adapter_injected_at_deployment"}))
    capabilities.register(CapabilityDescriptor("engineering.worker", "local-worker-runtime", None, True, "bounded", permission="tool.request"))
    capabilities.register(CapabilityDescriptor("research.local", "local-document-provider", None, True, "read", permission="tool.request"))
    capabilities.register(CapabilityDescriptor("research.browser", "browser-adapter", None, False, "read", requires_internet=True, permission="tool.request"))
    capabilities.register(CapabilityDescriptor("perception.screen", "perception-adapter", None, False, "read", permission="tool.request", metadata={"continuous_capture": False, "raw_frame_retention": False}))


async def bootstrap_runtime(config: JarvisConfig | None = None) -> JarvisRuntime:
    runtime = create_runtime(config)
    await runtime.start()
    return runtime


@asynccontextmanager
async def running_runtime(config: JarvisConfig | None = None) -> AsyncIterator[JarvisRuntime]:
    runtime = await bootstrap_runtime(config)
    try:
        yield runtime
    finally:
        await runtime.shutdown()
