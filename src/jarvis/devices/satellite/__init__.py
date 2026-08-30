"""Typed Windows satellite protocol and connection registry."""

from .contracts import (
    CommandObservation,
    CoreWelcome,
    SatelliteCommand,
    SatelliteHeartbeat,
    SatelliteHello,
)
from .registry import WindowsSatelliteRegistry
from .transport import ExpiredSatelliteSession, ResultSubmission, SatelliteTransportService

__all__ = [
    "CommandObservation",
    "CoreWelcome",
    "SatelliteCommand",
    "SatelliteHeartbeat",
    "SatelliteHello",
    "WindowsSatelliteRegistry",
    "ResultSubmission",
    "ExpiredSatelliteSession",
    "SatelliteTransportService",
]
