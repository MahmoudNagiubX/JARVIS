"""On-demand perception boundary."""

from .cache import ObservationCache
from .browser import BrowserDomPerceptionBridge
from .desktop import ActiveDesktopContextService
from .frame import TransientFrame, analyze_and_release
from .privacy import PerceptionPrivacyPolicy
from .providers import DeferredPerceptionProvider, StaticPerceptionProvider
from .windows import WindowsDesktopContextProvider, WindowsDesktopProvider
from .service import PerceptionService

__all__ = [
    "ActiveDesktopContextService", "BrowserDomPerceptionBridge", "DeferredPerceptionProvider", "ObservationCache",
    "PerceptionPrivacyPolicy", "PerceptionService", "StaticPerceptionProvider",
    "TransientFrame", "WindowsDesktopContextProvider", "WindowsDesktopProvider", "analyze_and_release",
]
