# JARVIS-owned model cleanup report

Inventory scope was limited to the repository's clearly JARVIS-owned model,
cache, asset, and data roots. No unrelated owner directory was scanned or
modified.

| Path | Identity | Size | SHA-256 | Decision |
|---|---|---:|---|---|
| None found in the repository-owned roots | — | 0 bytes | — | No unattended deletion |

The active local capability remains `Qwen3.5-4B-Heretic`. The repository does
not contain its GGUF or the voice/OCR weights; those are external owner-managed
assets and were not scanned, copied, or deleted. Any large unused model outside
a clearly JARVIS-owned model/cache directory requires a separate owner review.

Bytes freed: `0`.

No model deletion is claimed by this report.
