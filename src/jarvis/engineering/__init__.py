"""Engineering copilot services and provider adapters."""

from .providers import InMemoryEngineeringProvider, JupyterEngineeringProvider, KiCadEngineeringProvider
from .service import EngineeringService, EngineeringWorker

__all__ = [
    "EngineeringService", "EngineeringWorker", "InMemoryEngineeringProvider",
    "JupyterEngineeringProvider", "KiCadEngineeringProvider",
]
