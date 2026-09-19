# Local model policy

## Local-only rule

No model is downloaded, copied, loaded, hashed, repaired, or invoked as a
side effect of import/bootstrap. An explicitly configured local runtime may
invoke the exact `Qwen3.5-4B-Heretic` GGUF through the provider-neutral
gateway and bounded llama.cpp supervisor. Ollama is a loopback compatibility
adapter only; hybrid mode does not assume it exists.

## Observed local inventory

The bounded 2026-09-19/20 workstation audit verified the JARVIS-owned
llama.cpp runtime and the exact owner-provisioned Heretic 4B GGUF. The active
model is checksum-verified, served on loopback, and passed fresh startup and
generation checks; see `docs/audits/JARVIS_LOCAL_MODEL_READINESS.md`.
The existing external owner-managed BMO model root still contains a 9B Heretic
GGUF and an `.invalid-resume` artifact; neither is accepted or auto-selected
for the required 4B capability. No Ollama or LM Studio runtime was added or
used. The local server is owned and cleaned up by the single JARVIS supervisor.

## Required controls before model integration

- Use an explicit local allowlist by role: primary, embeddings, advanced, and
  voice where applicable.
- Record provider, model id, digest/checksum, capability, modality, context
  budget, and local-only status in the model gateway.
- Refuse missing, mismatched, or unapproved model identity. The production
  local identity is exactly `Qwen3.5-4B-Heretic` and the main GGUF filename
  must contain that identity; standard Qwen, 9B, projector, and partial files
  are rejected.
- Keep model storage isolated from source checkout and preserve the existing
  isolated store.
- Do not introduce public bindings or download-on-start behavior.
- Route all model tool proposals through the common tool authority path.
- Record health and model selection in correlated audit/events without storing
  secrets.
- Validate model licensing and redistribution terms before any product
  distribution.

The policy is the guardrail for Mega Phase 02 model integration. Optional
smoke testing may contact an already-running loopback provider, but does not
authorize model downloads, model-store mutation, or public bindings.
