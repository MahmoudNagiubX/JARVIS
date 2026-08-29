# Home automation

Home Assistant and MQTT are optional local transports behind product-owned
contracts. `HomeAssistantTransport` uses an injected or standard-library HTTP
requester for `/api/states` and allowlisted service calls. Tokens are never
written to events or audit metadata. `InMemoryHomeTransport` supplies a
deterministic offline test path.

The home authority permits reading entities and safe controls such as light
on/off, brightness, color, scenes, temperature, and restricted MQTT publish.
Locks, alarms, security overrides, and life-safety overrides are blocked by
default. MQTT topics must use configured `jarvis/` or `home/` prefixes and
bounded payloads; unrestricted publish and subscribe are not exposed.

A configured Home Assistant or MQTT broker is not assumed by the default
runtime. Adapter absence is reported as unavailable/deferred rather than as a
successful physical action. Successful dry runs are contract simulations.
