# Phase 16: Security & Privacy Model

## 1. Local-First Boundary
JARVIS operates under a zero-cloud-memory architecture:
- No remote vector database (e.g. Pinecone, Qdrant Cloud, Weaviate Cloud).
- No cloud embedding provider calls (all ranking uses deterministic keywords and local seams).
- No telemetry, analytics, or background sync to external cloud servers.
- All persistent data resides exclusively in the local SQLite WAL database on the owner's machine.

## 2. Credential & Secret Protection
`MemoryPolicy` actively prevents sensitive data from leaking into the persistent memory store:
- Passwords, passcodes, and PINs are blocked.
- API keys (`sk-`, `ghp_`, `glpat-`) are blocked.
- Bearer tokens, JWTs, OAuth refresh tokens, and session cookies are blocked.
- Private encryption and SSH keys are blocked.
- Credit card numbers are blocked.

## 3. Untrusted Source Injection Firewall
Memory extraction evaluates provenance before persistence:
- Candidates originating from `"browser"`, `"web"`, `"research"`, or untrusted scrapers cannot inject policy overrides (`SYSTEM:`, `override policy`, `owner authorized`, `disable approvals`).
- Untrusted candidates are capped at 0.6 confidence and restricted to factual categories without administrative authority.

## 4. Cross-Owner & Cross-Device Isolation
Every table in the SQLite database enforces `owner_id` scoping:
- `memories`, `goals`, `missions`, `world_facts`, `world_observations`, and `findings` are queried strictly by authenticated `owner_id`.
- Multiple devices bound to an owner use scoped cryptographic tokens.
- Cross-owner data access is strictly impossible at the query layer.

## 5. Surveillance Prevention
JARVIS enforces strict privacy boundaries around ambient media:
- Raw audio streams are never stored in memory or database records.
- Raw video frames and high-frequency screenshots are never persisted to long-term memory.
- Perception only captures structured, low-dimensional operational metadata (e.g. active window process name, window title) bounded by explicit session policies.
