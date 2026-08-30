"""Typed Windows satellite protocol and connection registry."""

from .contracts import (
    CommandObservation,
    CoreWelcome,
    SatelliteCommand,
    SatelliteHeartbeat,
    SatelliteHello,
)
from .registry import WindowsSatelliteRegistry
from .transport import ResultSubmission, SatelliteTransportService

__all__ = [
    "CommandObservation",
    "CoreWelcome",
    "SatelliteCommand",
    "SatelliteHeartbeat",
    "SatelliteHello",
    "WindowsSatelliteRegistry",
    "ResultSubmission",
    "SatelliteTransportService",
]
