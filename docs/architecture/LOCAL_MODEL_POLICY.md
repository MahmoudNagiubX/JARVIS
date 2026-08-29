# Local model policy

## Phase 01 rule

No model is downloaded, copied, loaded, hashed, repaired, or invoked by the
foundation. `src/jarvis` has no model-runtime or network dependency.

## Observed local inventory

Phase 00 found an isolated Ollama-style store under
`C:\Users\mahmo\BMO\phase-08-5-runtime\ollama-isolated-models` with manifests
for `bge-m3/567m`, `qwen3.5/4b`, and `qwen3.5-heretic/9b-q4km`. It also found
large GGUF/blob artifacts and approximately 16.36 GB free on the system drive.
These are inventory facts only; no artifact was opened or copied in Phase 01.

## Required controls before model integration

- Use an explicit local allowlist by role: primary, embeddings, advanced, and
  voice where applicable.
- Record provider, model id, digest/checksum, capability, modality, context
  budget, and local-only status in the model gateway.
- Refuse missing, mismatched, or unapproved model identity.
- Keep model storage isolated from source checkout and preserve the existing
  isolated store.
- Do not introduce public bindings or download-on-start behavior.
- Route all model tool proposals through the common tool authority path.
- Record health and model selection in correlated audit/events without storing
  secrets.
- Validate model licensing and redistribution terms before any product
  distribution.

The policy is a guardrail for Mega Phase 02 model integration; it does not
authorize any model operation during Phase 01.
