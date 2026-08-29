"""Dependency composition and lifecycle for the Phase 01 foundation."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import AsyncIterator
from uuid import uuid4

from .bus import InMemoryEventBus
from .config import JarvisConfig
from .contracts import (
    ApprovalEngine,
    AuditService,
    BrowserController,
    CommunicationChannel,
    ComputerController,
    GoalEngine,
    IdentityService,
    LLMRouter,
    MemoryStore,
    PermissionEngine,
    RealtimeVoiceSession,
    SpeechToText,
    TextToSpeech,
    ToolRegistry,
    WorldState,
)
from .events import Event, EventCategory, EventState
from .runtime.noop import (
    EmptyToolRegistry,
    FailClosedPermissionEngine,
    InMemoryApprovalEngine,
    InMemoryAuditService,
    InMemoryGoalEngine,
    InMemoryMemoryStore,
    InMemoryWorldState,
    NoOpBrowserController,
    NoOpCommunicationChannel,
    NoOpComputerController,
    NoOpIdentityService,
    NoOpLLMRouter,
    NoOpRealtimeVoiceSession,
    NoOpSpeechToText,
    NoOpTextToSpeech,
)


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
    identity: IdentityService
    permission: PermissionEngine
    approval: ApprovalEngine
    audit: AuditService
    models: LLMRouter
    tools: ToolRegistry
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
        await self.event_bus.publish(
            Event.create(
                "system.bootstrap.started",
                EventCategory.SYSTEM,
                correlation_id=correlation_id,
                payload={"service_name": self.config.service_name},
            )
        )
        self.state = RuntimeState.READY
        await self.event_bus.publish(
            Event.create(
                "system.bootstrap.ready",
                EventCategory.SYSTEM,
                correlation_id=correlation_id,
                state=EventState.COMPLETED,
                payload={"environment": self.config.environment},
            )
        )

    async def shutdown(self) -> None:
        if self.state is RuntimeState.STOPPED:
            return
        if self.state is not RuntimeState.READY:
            raise RuntimeError(f"cannot shut down runtime from {self.state.value}")
        self.state = RuntimeState.STOPPING
        await self.event_bus.publish(
            Event.create(
                "system.shutdown.started",
                EventCategory.SYSTEM,
                correlation_id=self.runtime_id,
            )
        )
        await self.event_bus.publish(
            Event.create(
                "system.shutdown.completed",
                EventCategory.SYSTEM,
                correlation_id=self.runtime_id,
                state=EventState.COMPLETED,
            )
        )
        self.state = RuntimeState.STOPPED
        await self.event_bus.close()


def create_runtime(config: JarvisConfig | None = None) -> JarvisRuntime:
    """Compose the foundation without opening I/O or loading any model."""

    return JarvisRuntime(
        config=config or JarvisConfig.from_env(),
        event_bus=InMemoryEventBus(),
        identity=NoOpIdentityService(),
        permission=FailClosedPermissionEngine(),
        approval=InMemoryApprovalEngine(),
        audit=InMemoryAuditService(),
        models=NoOpLLMRouter(),
        tools=EmptyToolRegistry(),
        memory=InMemoryMemoryStore(),
        world_state=InMemoryWorldState(),
        goals=InMemoryGoalEngine(),
        computer=NoOpComputerController(),
        browser=NoOpBrowserController(),
        voice=NoOpRealtimeVoiceSession(),
        stt=NoOpSpeechToText(),
        tts=NoOpTextToSpeech(),
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
