# JARVIS personalization

Personalization is an editable owner-scoped profile, not hidden model state.
Defaults are preferred name Mahmoud, alternate address Sir, assistant name
JARVIS, concise verbosity, calm/formal/intelligent tone, and Egyptian Arabic
with English technical terms. Notification tolerance and bounded preference
fields are also supported.

Explicit updates and narrowly recognized conversation signals can update the
profile. Every change records its source, emits `personalization.updated`, and
can be reset through the service. Context assembly injects only the profile
needed for the current request and includes the offline state.

The loopback API exposes `GET/PATCH /v1/personalization/profile`.

