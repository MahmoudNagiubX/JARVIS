# Research runtime

Research is a bounded, local-first service under `jarvis.research`. Its
pipeline is request, plan, search, bounded read, evidence ledger,
deduplication, cross-check, deterministic synthesis, citation validation, and
report. Resource limits cover steps, sources, context, time, and cancellation.

`LocalDocumentProvider` works offline over configured document roots and
allowlisted text-like suffixes. `BrowserResearchProvider` and the SearXNG seam
are injected adapters; no Tavily or hosted search client is required. The
default runtime therefore makes no web-research availability claim.

Source text is untrusted data. Evidence stores a bounded excerpt, locator, and
fingerprint; it does not execute instructions found in a page or document and
does not retain a whole copyrighted page. Citations point to ledger evidence,
and report limitations state when no hosted model synthesis was used.
