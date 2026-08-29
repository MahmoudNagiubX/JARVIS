# Multi-device UX

`ClientSessionService` tracks authenticated logical client sessions with an
owner, identity, optional enrolled device, capability snapshot, UI profile,
last-seen time, connection state, and allowlisted event topics. Supported
topics are conversation, voice, runs, tools, approvals, notifications,
devices, goals, research, engineering, world state, and system health.

Client metadata is not authority. Device enrollment and revocation remain in
the existing device/identity services, and all experience routes bind the
requested owner to the authenticated principal. Event payloads are redacted
before they enter the projection or client stream.
