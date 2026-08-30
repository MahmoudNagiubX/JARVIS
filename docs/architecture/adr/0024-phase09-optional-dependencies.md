# ADR 0024: Keep live dependencies optional

- Status: accepted
- Date: 2026-08-30

## Decision

The base package stays dependency-free. Optional audio, model, browser,
database, SSH, or node integrations are installed and configured outside the
core runtime, with capability and health states reported explicitly.

## Consequence

Bootstrap remains deterministic and local; unavailable hardware or services
cannot become false success.
