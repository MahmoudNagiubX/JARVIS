# JARVIS-owned model cleanup report

Inventory scope was limited to the repository's clearly JARVIS-owned model,
cache, asset, and data roots plus the explicitly configured local runtime.
No unrelated owner directory was scanned or modified.

| Path/surface | Identity | Size | SHA-256 | Decision |
|---|---|---:|---|---|
| JARVIS model root | exact `Qwen3.5-4B-Heretic-Q4_K_M.gguf` | 2,708,804,384 bytes | `E09C792EFC37446E3D31DFC7C9B91B8A6CEB7768DCD3EFE0A8F9D287C1A74579` | Preserve; it is the active configured model |
| JARVIS llama.cpp runtime | `llama-server.exe` b10690 | 9,216 bytes | See readiness report | Preserve; it is the configured runtime |

The active local capability remains `Qwen3.5-4B-Heretic`. The bounded audit
observed a legacy external 9B Heretic GGUF and `.invalid-resume` artifact under
the BMO root; they were not opened, hashed, copied, renamed, repaired, or deleted.
They must not be removed until a separate usage review proves they are unused
by active voice/OCR or other owner configuration. Any large model outside a
clearly JARVIS-owned model/cache directory requires separate owner review.

Bytes freed: `0`.

No model deletion is claimed by this report.
