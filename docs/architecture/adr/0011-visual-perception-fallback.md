# ADR 0011: Visual perception is deterministic-first and on-demand

Status: Accepted

## Decision

Use native/UIAutomation or browser structure before OCR, local vision, and
visual fallback. Capture is explicit and on-demand. Raw frames are not
durable state; camera and continuous capture are disabled by default.

## Consequences

The product can operate when OCR or local vision is absent by returning a
typed deferred capability. OmniParser/UI-TARS and model-backed perception are
future provider adapters, not dependencies of the core.
