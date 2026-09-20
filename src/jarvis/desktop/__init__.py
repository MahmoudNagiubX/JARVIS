"""Zero-touch local desktop productization for JARVIS.

The desktop package is deliberately an orchestration boundary.  It composes
the existing runtime, identity service, VoiceCore, model supervisor, and HUD;
it does not create a second domain authority.
"""

from .config import DesktopProductConfig, ProductConfigError, product_config_path
from .lifecycle import DesktopPhase, DesktopStatus, JarvisDesktopLifecycle
from .model import LocalModelDiscovery, LocalModelReferences
from .secret_store import (
    CLOUD_PROVIDER_SECRET_KEYS,
    LocalSecretStore,
    MemorySecretStore,
    cloud_provider_secret_states,
    cloud_secret_key,
    platform_secret_store,
    read_cloud_provider_keys,
)

__all__ = [
    "DesktopPhase",
    "DesktopProductConfig",
    "DesktopStatus",
    "JarvisDesktopLifecycle",
    "LocalModelDiscovery",
    "LocalModelReferences",
    "LocalSecretStore",
    "MemorySecretStore",
    "CLOUD_PROVIDER_SECRET_KEYS",
    "ProductConfigError",
    "cloud_provider_secret_states",
    "cloud_secret_key",
    "platform_secret_store",
    "product_config_path",
    "read_cloud_provider_keys",
]
