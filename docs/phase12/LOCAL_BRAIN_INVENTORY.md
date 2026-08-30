# Phase 12 local brain inventory

Inventory date: 2026-08-30, host `NIGHTFURY`, Windows 11 Home Single
Language, Python 3.14.

## Bounded discovery

- CPU: Intel Core i7-12700H, 14 physical cores / 20 logical processors.
- Memory: 16,011 MB visible RAM. Free RAM was approximately 887 MB during
  the physical attempt; this is a constrained workstation configuration.
- GPU: NVIDIA GeForce RTX 4050 Laptop GPU, 6,141 MiB VRAM; approximately
  4,225 MiB was free at the preflight probe. Intel UHD was also present.
- System disk: approximately 24.36 GB free at discovery.
- No Ollama, `llama-server`, `llama-cli`, or `llama-bench` was present on
  `PATH` before this phase.
- No model weights were downloaded, copied, imported, moved, or deleted.

One existing valid-looking GGUF was found at the bounded search scope in an
external legacy BMO model directory. Public documentation intentionally
records only the basename and directory class:

- basename: `Qwen3.5-9B-ultra-uncensored-heretic-v2-Q4_K_M.gguf`
- size: `5,527,953,952` bytes
- last-write date: 2026-08-19
- candidate count: 1
- selected alias: `jarvis-local-qwen`

The model was read in place. The protected BMO repository and its evidence
files were not modified.

## Runtime selection

The official llama.cpp Windows CUDA 12.4 release `b10690` was installed
outside the repository under the user-local JARVIS runtime directory. The
package reports `0.3.0-dev`, build `10690`, commit `bdf395515` and includes
the CUDA 12.4 libraries required by the selected RTX 4050 path. The binary
was checksum-verified against the published release digest before use.

The product command is loopback-only, uses `shell=False`, and passes only the
validated model, host, port, context, threads, GPU-layer, alias, and no-webui
arguments. No model binary or runtime binary is tracked in this repository.
