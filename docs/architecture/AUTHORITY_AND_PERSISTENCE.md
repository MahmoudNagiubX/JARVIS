# Authority and persistence

Identity and device authority is adapted from the BMO Phase 06 shape:

- an owner has one or more product identities;
- devices are owner-bound and carry explicit scopes/capabilities;
- one-time enrollment codes and device credentials are returned only at
  issuance time;
- only salted PBKDF2 hashes and public credential ids are persisted;
- authentication checks credential, device status, owner status, and binding;
- device revocation invalidates its credentials.

Permission evaluation fails closed for missing authority, owner mismatch,
missing scope/capability, critical risk, and unknown actions. Safe reads and
reversible fixtures may be allowed; consequential tools require a durable
approval decision.

`RuntimeRepository` is the only persistence service boundary. The SQLite
adapter persists the relational runtime records listed in
`CORE_RUNTIME.md`. `persistence/migrations/001_initial.sql` records the
migration boundary; the schema is created by the zero-install adapter for
local operation. PostgreSQL migration, pooling, and pgvector are intentionally
deferred adapter work.
