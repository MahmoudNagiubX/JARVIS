# Capability registry

`CapabilityRegistry` is the runtime inventory of currently exposed product
capabilities. Each descriptor names its provider, optional device, availability,
risk, permission class, and environmental requirements such as internet,
local network, or device liveness.

The registry is informational and fail-closed: unavailable capabilities are
excluded by default, and registration does not grant permission. Actual use
still passes identity/device authority, capability checks, policy, approval
when required, audit, and event emission. The context assembler includes the
registered capability ids so the agent can distinguish available local paths
from deferred adapters.
