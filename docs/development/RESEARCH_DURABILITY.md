# Research durability

Research runs, steps, sources, evidence fingerprints, untrusted-content flags,
and reports are persisted in `research_runs`, `research_sources`, and
`research_evidence`. On process restart, transient queued/running/planning/
searching/reading/synthesizing rows are marked failed with
`process_restarted`; completed ledgers remain readable.

The current standard-library HTTP path executes a bounded run in the request
loop, so it cannot leave an orphan task behind. Durable background pause,
resume, and multi-process job claiming remain a follow-up adapter rather than
being simulated in this phase. Browser provider calls are time-bounded by the
request budget.
