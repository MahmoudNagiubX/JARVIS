# ADR 0004: Authority precedes capability execution

- Status: accepted
- Date: 2026-08-29

## Decision

Identity and device context precede permission evaluation. Consequential work
requires explicit approval, audit records, device/capability binding,
execution, verification, and outcome audit. Models and voice sessions may
propose or collect a decision but may not self-authorize.

## Consequences

Every future tool, computer, browser, communication, or worker adapter must
accept the common context and follow the same ordering. Convenience paths that
bypass the authority plane are not part of the target architecture.
