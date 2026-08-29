"""Runtime composition and safe Phase 01 implementations."""

from .noop import (
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
from .lifecycle import LifecycleSnapshot, RuntimeLifecycle

__all__ = [
    "EmptyToolRegistry",
    "FailClosedPermissionEngine",
    "InMemoryApprovalEngine",
    "InMemoryAuditService",
    "InMemoryGoalEngine",
    "InMemoryMemoryStore",
    "InMemoryWorldState",
    "NoOpBrowserController",
    "NoOpCommunicationChannel",
    "NoOpComputerController",
    "NoOpIdentityService",
    "NoOpLLMRouter",
    "NoOpRealtimeVoiceSession",
    "NoOpSpeechToText",
    "NoOpTextToSpeech",
    "LifecycleSnapshot",
    "RuntimeLifecycle",
]
