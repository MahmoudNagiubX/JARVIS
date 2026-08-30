"""Typed Windows satellite protocol and connection registry."""

from .contracts import (
    CommandObservation,
    CoreWelcome,
    SatelliteCommand,
    SatelliteHeartbeat,
    SatelliteHello,
    PERCEPTION_PROTOCOL_VERSION,
    PROTOCOL_VERSION,
    validate_perception_output,
)
from .registry import WindowsSatelliteRegistry
from .transport import ExpiredSatelliteSession, ResultSubmission, SatelliteTransportService

__all__ = [
    "CommandObservation",
    "CoreWelcome",
    "SatelliteCommand",
    "SatelliteHeartbeat",
    "SatelliteHello",
    "PROTOCOL_VERSION",
    "PERCEPTION_PROTOCOL_VERSION",
    "validate_perception_output",
    "WindowsSatelliteRegistry",
    "ResultSubmission",
    "ExpiredSatelliteSession",
    "SatelliteTransportService",
]
