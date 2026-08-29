"""Dependency composition and lifecycle for the Phase 02 core runtime."""

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
from .computer.controller import WindowsComputerController
from .contracts import (
    ApprovalEngine,
    AuditService,
    BrowserController,
    CommunicationChannel,
    ComputerController,
    GoalEngine,
    MemoryStore,
    PermissionEngine,
    RealtimeVoiceSession,
    SpeechToText,
    TextToSpeech,
    WorldState,
)
from .devices.satellite.registry import WindowsSatelliteRegistry
from .events import Event, EventCategory, EventState
from .models.gateway import ModelGateway
from .persistence.db import SQLiteDatabase
from .persistence.repositories import RuntimeRepository
from .runtime.noop import (
    InMemoryGoalEngine,
    InMemoryMemoryStore,
    InMemoryWorldState,
    NoOpBrowserController,
    NoOpCommunicationChannel,
    NoOpSpeechToText,
    NoOpTextToSpeech,
)
from .tools.registry import ToolRegistry, default_registry
from .tools.service import ToolExecutionService
from .voice.core import VoiceCore


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
    memory: MemoryStore
    world_state: WorldState
    goals: GoalEngine
    computer: ComputerController
    browser: BrowserController
    voice: RealtimeVoiceSession
    stt: SpeechToText
    tts: TextToSpeech
    communication: CommunicationChannel
    runtime_id: str
    state: RuntimeState = RuntimeState.CREATED

    async def start(self) -> None:
        if self.state is RuntimeState.READY:
            return
        if self.state is not RuntimeState.CREATED:
            raise RuntimeError(f"cannot start runtime from {self.state.value}")
        self.state = RuntimeState.STARTING
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
    agent = AgentRuntime(repository, event_bus, models, tool_service, max_steps=effective_config.max_agent_steps)
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
        memory=InMemoryMemoryStore(),
        world_state=InMemoryWorldState(),
        goals=InMemoryGoalEngine(),
        computer=WindowsComputerController(satellite),
        browser=NoOpBrowserController(),
        voice=VoiceCore(agent, event_bus, stt, tts),
        stt=stt,
        tts=tts,
        communication=NoOpCommunicationChannel(),
        runtime_id=f"runtime-{uuid4()}",
    )


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
