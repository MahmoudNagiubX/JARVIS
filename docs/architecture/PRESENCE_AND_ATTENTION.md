# Presence and Attention

`PresenceService` derives a transient owner-scoped projection from explicit
voice endpoint activity, authenticated client sessions, device heartbeats,
originating devices, and room assignments. Each observation has provenance,
confidence, freshness, device identity, optional room, and a World State TTL.
There is no continuous microphone/camera monitoring, keystroke logging, or
automatic Memory promotion.

`AttentionPolicy` decides whether a notification is delivered now, queued,
visual-only, or announced on a trusted endpoint. Quiet hours and focus/study,
meeting, sleep, away, and do-not-disturb modes reduce interruption. Urgency
only changes delivery behavior; it never increases action authority.
