"""Typed Windows satellite protocol and connection registry."""

from .contracts import (
    CommandObservation,
    CoreWelcome,
    SatelliteCommand,
    SatelliteHeartbeat,
    SatelliteHello,
)
from .registry import WindowsSatelliteRegistry

__all__ = [
    "CommandObservation",
    "CoreWelcome",
    "SatelliteCommand",
    "SatelliteHeartbeat",
    "SatelliteHello",
    "WindowsSatelliteRegistry",
]
