# Windows satellite

The core exposes a typed Windows satellite protocol with versioned hello,
welcome, heartbeat, command, and observation records. The existing registry
is wrapped by the authenticated HTTP long-poll transport documented in
`NODE_TRANSPORT.md`; it checks protocol version, owner/device identity, and
declared capabilities.

The computer controller accepts only `observe` and `input`, translating them
to `computer.observe` and `computer.input` commands. It does not execute
arbitrary shell text. The intended implementation order is native Windows
API, UI Automation, then a product-owned UFO adapter boundary, followed later
by vision assistance. Microsoft UFO is not merged or imported.

The runtime provides reconnect, capability advertisement, status inspection,
bounded queues/TTL, replay idempotency, heartbeat freshness, and revocation
helpers while retaining the typed command boundary. The runnable Windows
client and its acceptance contract are in `WINDOWS_SATELLITE_LIVE.md`.
Physical UI automation and a real deployed process remain separate acceptance
items; dry-run and in-process tests do not claim physical PASS.
