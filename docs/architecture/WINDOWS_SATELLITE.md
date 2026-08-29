# Windows satellite

The core exposes a typed Windows satellite protocol with versioned hello,
welcome, heartbeat, command, and observation records. A registry binds a
Windows device to a live in-process connection and checks protocol version,
owner/device identity, and declared capabilities.

The computer controller accepts only `observe` and `input`, translating them
to `computer.observe` and `computer.input` commands. It does not execute
arbitrary shell text. The intended implementation order is native Windows
API, UI Automation, then a product-owned UFO adapter boundary, followed later
by vision assistance. Microsoft UFO is not merged or imported.

Phase 04 adds reconnect, capability advertisement, status inspection, and
revocation helpers while retaining the typed command boundary. The protocol
and mock handler are tested in-process. Physical Windows UI automation,
transport security, and a real satellite process remain partial acceptance
items.
