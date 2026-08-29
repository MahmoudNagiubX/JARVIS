# JARVIS memory

JARVIS owns the memory contract and policy. Memory is durable, owner-scoped
information; current observations remain in World State instead.

## Model

`MemoryRecord` stores category, content, optional structured data, provenance,
timestamps, confidence, sensitivity, scope, retention, status, tags, pin/archive
state, and supersession information. Supported categories are profile,
preference, project, task, goal, relationship, workflow, technical_context,
device_context, habit, fact, decision, and conversation_summary.

Useful conversation signals pass through candidate extraction, policy,
deduplication/conflict detection, and durable persistence. Filler, secrets,
raw media, and card-like data are rejected by default. Conflicting structured
facts supersede the older active record and retain an auditable link.

## Retrieval and control

Retrieval applies owner/category/source/tag filters, then deterministic exact and
keyword ranking. The `EmbeddingProvider` protocol is vector-ready, but no
embedding model is required or downloaded. Mem0, Cognee, and Graphiti were
evaluated as reference concepts only; no adapter is selected in this phase.

The service supports list/search, inspect, edit/correct, delete, forget by
category, pin, archive, and maintenance. Mutations emit memory events and write
audit records. HTTP adapters expose `/v1/memory`, `/v1/memory/search`, and
authenticated edit/delete operations.

SQLite is the default zero-install durable adapter. PostgreSQL DDL is staged as
a migration boundary, while the current product repository remains SQLite-first.

