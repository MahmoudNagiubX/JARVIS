# Multi-Room Voice Fabric

## Centralized Voice Architecture
`RoomVoiceFabric` coordinates multi-room audio while strictly reusing the single authoritative `VoiceCore` and `AgentRuntime` on NIGHTFURY.

```
+-------------------------------------------------------------------------------+
| Room Microphone (Living Room)                                                 |
| -> RoomUtteranceEnvelope (session_id, endpoint_id, text/audio)                |
+---------------------------------------+---------------------------------------+
                                        |
                                        v
+-------------------------------------------------------------------------------+
| RoomVoiceFabric (NIGHTFURY)                                                   |
| - Resolves endpoint via VoiceRoutingService (endpoint_id -> living_room)      |
| - Transcribes audio (ephemeral in-memory STT)                                 |
| - Passes transcript to single VoiceCore.process_transcript()                  |
| - VoiceCore runs single AgentRuntime turn -> synthesizes response audio       |
| - Dispatches RoomPlaybackEnvelope back to originating room speaker           |
+---------------------------------------+---------------------------------------+
                                        |
                                        v
+-------------------------------------------------------------------------------+
| Room Speaker (Living Room)                                                    |
| -> Plays synthesized audio response                                           |
+-------------------------------------------------------------------------------+
```

## Barge-In & Cancellation
- When a user speaks while audio is playing, `RoomVoiceFabric.barge_in()` cancels the active `_agent_task`, `_tts_task`, and `_playback_task` in `VoiceCore`.
- Interrupted turns return `RoomPlaybackEnvelope(interrupted=True, text="")`.
- **Zero Raw Audio Retention**: Raw audio buffers are ephemeral in memory and explicitly deleted (`del audio`) immediately following synthesis/transcription.
