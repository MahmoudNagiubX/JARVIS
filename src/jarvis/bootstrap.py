"""Dependency composition and lifecycle for the Phase 03 core runtime."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import AsyncIterator
from uuid import uuid4

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
)
from .devices.satellite.registry import WindowsSatelliteRegistry
from .devices.fabric import DeviceFabricService
from .devices.home.service import HomeActionService, RestrictedMQTTTransport
from .events import Event, EventCategory, EventState
from .models.gateway import ModelGateway
from .models.routing import ModelRoute
from .persistence.db import SQLiteDatabase
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
    runtime_id: str
    state: RuntimeState = RuntimeState.CREATED

    async def start(self) -> None:
        if self.state is RuntimeState.READY:
            return
        if self.state is not RuntimeState.CREATED:
            raise RuntimeError(f"cannot start runtime from {self.state.value}")
        self.state = RuntimeState.STARTING
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
        self.state = RuntimeState.STOPPED
        self.database.close()
        await self.event_bus.close()


def create_runtime(config: JarvisConfig | None = None) -> JarvisRuntime:
    """Compose the foundation without opening I/O or loading any model."""

    effective_config = config or JarvisConfig.from_env()
    database_path = ":memory:" if effective_config.environment in {"test", "offline-test"} else effective_config.database_path
    database = SQLiteDatabase(database_path)
    repository = RuntimeRepository(database)
    event_bus = InMemoryEventBus()
    permission = PolicyPermissionEngine()
    approval = DurableApprovalEngine(repository)
    audit = DurableAuditService(repository)
    registry = default_registry()
    tool_service = ToolExecutionService(repository, event_bus, registry, permission, approval, audit)
    models = ModelGateway(effective_config)
    satellite = WindowsSatelliteRegistry()
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

    async def maintenance_owner() -> str | None:
        owner = repository.first_owner()
        return str(owner["id"]) if owner else None

    async def maintain_memory() -> dict[str, int]:
        owner_id = await maintenance_owner()
        return await memory.maintain(owner_id) if owner_id else {"expired": 0, "archived": 0}

    async def expire_world_state() -> int:
        owner_id = await maintenance_owner()
        return await world_state.expire(owner_id) if owner_id else 0

    async def detect_proactive() -> int:
        owner_id = await maintenance_owner()
        return len(await proactive.detect(owner_id)) if owner_id else 0

    async def refresh_health() -> dict[str, object]:
        await offline.refresh()
        model_health = await models.health(ModelRoute.GENERAL_REASONING)
        return {"model": model_health.provider, "offline": offline.state.online}

    scheduler.add("memory-maintenance", 300, maintain_memory)
    scheduler.add("world-state-expiry", 60, expire_world_state)
    scheduler.add("goal-proactive-check", 60, detect_proactive)
    scheduler.add("health-check", 120, refresh_health)
    return JarvisRuntime(
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
        workspace=WorkspaceContextService(world_state),
        scheduler=scheduler,
        venom=VenomNode(),
        computer=WindowsComputerController(satellite),
        browser=browser_controller,
        voice=VoiceCore(agent, event_bus, stt, tts),
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
        runtime_id=f"runtime-{uuid4()}",
    )


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
    capabilities.register(CapabilityDescriptor(
        "device.venom.health", "venom", "venom", False, "read",
        metadata={"reason": "not_probed", "network": "unknown-until-deployment"},
    ))


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
