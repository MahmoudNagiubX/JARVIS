"""Computer control adapters."""

from .controller import UFOComputerController, WindowsComputerController
from .service import ComputerActionService, WindowsNativeComputerController

__all__ = ["ComputerActionService", "UFOComputerController", "WindowsComputerController", "WindowsNativeComputerController"]
