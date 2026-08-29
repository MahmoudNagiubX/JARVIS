# Room voice routing

`VoiceRoutingService` keeps endpoint and room routing metadata separate from
the realtime audio pipeline. Endpoints declare input/output availability,
online state, room, and owning user. A voice session replies on its
originating endpoint when possible; when that endpoint cannot output, the
service chooses an online output endpoint in the same room and records an
explicit handoff event.

Endpoint registration, online/offline state, mute changes, routing, and
handoff are deterministic and do not open microphones or speakers. Physical
voice acceptance still requires a separately configured hardware adapter and
is not claimed by these logical routing tests.
