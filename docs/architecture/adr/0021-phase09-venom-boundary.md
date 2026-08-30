# ADR 0021: Keep Venom deployment authorization explicit

- Status: accepted
- Date: 2026-08-30

## Decision

Do not guess or probe a Venom host, IP, SSH user, alias, or tunnel. Permit
physical integration only after an operator supplies an authorized target and
records the bounded tunnel and recovery evidence.

## Consequence

This workstation reports Venom as deferred and remains loopback-only.
