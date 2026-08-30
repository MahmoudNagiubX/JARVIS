# Ephemeral visual context

Visual observations are current-turn context. `TransientFrame` is an internal
buffer used only while an analyzer runs; it is released and zeroed on both
success and failure. `ScreenObservation` contains only bounded derived data
and always reports `raw_retained = false`.

`ObservationCache` is in-memory, owner/device/session-bound, TTL-limited to
60 seconds, and bounded to eight observations per owner and 32 total. Runtime
shutdown clears it. `screen.latest` never recaptures and cannot cross a
security boundary.

Visual tools are marked `ToolResultRetention.EPHEMERAL`. The full result may
reach the local model during the current run, but persisted run context stores
only a digest, source, observation reference, and `retained: false`. Events,
audit records, Memory, World State, messages, HUD state, and evidence do not
receive raw pixels or visual text.
