# ADR 0007: Preserve donor repositories and owner-owned evidence

- Status: accepted
- Date: 2026-08-29

## Decision

Only `C:\Jarivs\00_final\jarvis` may be modified during Phase 01. Donor
repositories, BMO worktrees, model stores, and owner-owned evidence remain
read-only. In particular, the existing Phase 10 voice-core evidence file is
never staged, stashed, overwritten, committed, or deleted.

## Consequences

Migration is performed through adapters or deliberate later copies with
explicit provenance. Git status checks are part of final validation.
