# Phase 16: Residual Risks & Phase 17 Integration Seams

## 1. Residual Risks & Mitigations

| Risk | Severity | Mitigation in Phase 16 |
|---|---|---|
| Memory bloat over extended run | Low | Strict keyword ranking limits context to top 6 items; `maintain()` auto-archives temporary memories and expires stale records. |
| Inaccurate Arabic technical extraction | Low | Dual-language regex patterns capture both Egyptian colloquialisms and MSA roots; fallback keyword retrieval matches raw normalized tokens. |
| Proactive detector false positives | Low | Cooldown hash deduplication suppresses identical findings for 1800-3600s; only high-confidence deterministic conditions trigger alerts. |
| Mission runaway tool execution | Low | Hard `MissionBudget` limits tool calls (<=25), steps (<=10), and execution duration (<=600s). |

## 2. Phase 17 Integration Seams (Prepared, Not Activated)

1. **Local Vector Provider Seam (`EmbeddingProvider` protocol)**:
   - Defined in `src/jarvis/memory/retrieval.py` as `EmbeddingProvider.embed(text)`.
   - In Phase 16, default retrieval uses zero-dependency deterministic `KeywordMemoryRetriever`.
   - Phase 17 can bind an on-device local embedding model (e.g. ONNX / llama.cpp embeddings) without altering `DurableMemoryService` or context contracts.

2. **Autonomous Multi-Agent Swarm Collaboration**:
   - `MissionService` supports worker run allocations and dependency graphs.
   - Phase 17 can instantiate specialized sub-worker runtimes while preserving the single-owner security perimeter.

3. **Perception-Guided Mission Re-planning**:
   - `MissionService.replan()` accepts perception-driven constraints.
   - Phase 17 can connect real-time desktop UI OCR and layout trees to automatically adjust mission execution steps.
