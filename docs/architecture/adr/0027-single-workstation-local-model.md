# ADR 0027: Select one workstation-local model

- Status: accepted
- Date: 2026-08-30

## Decision

The local boundary validates one owner-provisioned external GGUF in place
through one llama.cpp runtime package. The current required identity is
`Qwen3.5-4B-Heretic`; the constrained workstation does not get a second model
store or background model manager. Hybrid cloud fallback is a separate
capability route and is not used to misreport local readiness.

## Consequences

The selected identity and physical result are auditable without publishing a
personal absolute path or model prompts. Historical Phase 12 physical results
remain historical; the current exact Heretic GGUF/runtime combination is
`LOCAL_HERETIC_LIVE_READY` after owner download, checksum verification, and
fresh live multilingual/offline smoke. Exact private paths and observations
are kept in the owner-local readiness report.
