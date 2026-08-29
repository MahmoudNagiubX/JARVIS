# Venom deployment boundary

Phase 04 keeps Venom as a product-owned node descriptor and capability
consumer. It does not infer an address, open a remote session, deploy a
service, move local model files, or expose a public endpoint. `VenomNode` is
reported as unprobed until a later deployment task supplies an explicit,
authorized transport and evidence path.

Future deployment work must preserve loopback-first bindings, owner/device
authority, audit/event records, offline degradation, and the no-model-copy
policy. A node registration or health descriptor is not evidence that a
physical Venom host is reachable.
