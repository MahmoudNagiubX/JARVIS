# Device setup

1. Bootstrap the local owner through the normal runtime.
2. Create a short-lived enrollment for the device role, platform, scope, and
   least capabilities it needs.
3. Redeem the one-time enrollment on the device and keep the raw credential
   outside source control.
4. Register any additional fabric metadata such as room, transport, and trust
   only after the device is known and authorized.
5. Send bounded heartbeats. A stale device becomes offline and an offline or
   revoked device has no active fabric capabilities.

The default APIs stay loopback-only. Do not add public bindings, unrestricted
shell execution, arbitrary MQTT topics, or broad computer capabilities to make
setup convenient. Hardware, Playwright, Home Assistant, MQTT, and external
communication adapters are optional and must be configured explicitly.
