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
]
