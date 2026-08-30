# Venom node architecture

Venom is represented by a generic product-owned node descriptor with
`device_id=venom`, server role, capability names, and lightweight-only
inference metadata. The descriptor can plan future PostgreSQL, persistence,
scheduling, proactive watching, event relay, health, and backup-metadata roles.

This phase deliberately does not guess Venom's operating system, IP address,
or deployment layout. It does not remotely deploy, move Qwen assets, probe an
unknown host, or expose a network endpoint. `VenomNode.health()` therefore
reports `not_probed` until a later explicitly authorized deployment path exists.

The Phase 09 workstation inventory found no authorized Venom SSH alias, host,
or user. Tunnel guidance is intentionally placeholder-only in
`docs/development/TUNNEL_SETUP.md`; no physical Venom acceptance is claimed.
