# Phase 15 Research Architecture

`ResearchService` remains the research authority. The local provider searches
explicitly configured roots; the browser provider is optional and can degrade
when offline. The service performs bounded collection, cancellation,
deduplication, provenance/fingerprinting, and evidence-led synthesis.

Each evidence item is treated as untrusted source data and is linked to the
report citations. Source excerpts are bounded, malicious instructions remain
inside evidence text, and the synthesis cannot grant permission or execute a
tool. Research does not silently turn a web source into an executable MCP
capability.
