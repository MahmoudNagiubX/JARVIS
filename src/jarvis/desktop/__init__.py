"""Zero-touch local desktop productization for JARVIS.

The desktop package is deliberately an orchestration boundary.  It composes
the existing runtime, identity service, VoiceCore, model supervisor, and HUD;
it does not create a second domain authority.
"""

from .config import DesktopProductConfig, ProductConfigError, product_config_path
from .lifecycle import DesktopPhase, DesktopStatus, JarvisDesktopLifecycle
from .model import LocalModelDiscovery, LocalModelReferences
from .secrets import LocalSecretStore, MemorySecretStore, platform_secret_store

__all__ = [
    "DesktopPhase",
    "DesktopProductConfig",
    "DesktopStatus",
    "JarvisDesktopLifecycle",
    "LocalModelDiscovery",
    "LocalModelReferences",
    "LocalSecretStore",
    "MemorySecretStore",
    "ProductConfigError",
    "platform_secret_store",
    "product_config_path",
]
