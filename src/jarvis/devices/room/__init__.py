"""Room-facing device boundary; physical audio remains outside the core."""

from ...voice.routing.service import VoiceRoutingService

RoomRouter = VoiceRoutingService

__all__ = ["RoomRouter", "VoiceRoutingService"]
