"""Computer control adapters."""

from .applications import (
    ApplicationCandidate,
    ApplicationClass,
    ApplicationLaunchKind,
    ApplicationLoginStatus,
    AutomationTier,
    InstalledApplication,
    InstalledApplicationRegistry,
    SurfacePreference,
)
from .controller import ComputerExecutionRouter, UFOComputerController, WindowsComputerController
from .service import ComputerActionService, WindowsNativeComputerController

__all__ = [
    "ApplicationCandidate", "ApplicationClass", "ApplicationLaunchKind", "ApplicationLoginStatus",
    "AutomationTier", "InstalledApplication", "InstalledApplicationRegistry", "SurfacePreference",
    "ComputerActionService", "ComputerExecutionRouter", "UFOComputerController", "WindowsComputerController",
    "WindowsNativeComputerController",
]
