# Mission debugging

Inspect the mission row, plan, current step, budget counters, checkpoint
records, evidence records, and correlated events. Call `validate` before
`start`; use `advance`/`complete_step` for one bounded step at a time. A
consequential step should be expected to pause for approval. Replan only with
a concrete failure, unavailable capability, material world-state change, or
changed user constraint, and verify the remaining replan budget.
