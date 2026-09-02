"""Room-facing device boundary; physical audio remains outside the core."""

from ...voice.routing.service import VoiceRoutingService
from .service import RoomService

RoomRouter = VoiceRoutingService

__all__ = ["RoomRouter", "RoomService", "VoiceRoutingService"]
