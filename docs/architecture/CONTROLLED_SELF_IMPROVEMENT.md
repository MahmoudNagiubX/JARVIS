# Controlled self-improvement

Allowed adaptation is limited to personalization, memory, skill drafts,
automation proposals, routing/notification preferences, and workspace
metadata. `ControlledImprovementPolicy` can create a reviewable proposal, but
`can_apply_automatically` is always false.

Source changes follow the ordinary scoped developer-worker, diff review, test,
and human approval workflow. JARVIS cannot silently modify its own source,
authority rules, deployment, or protected donor/BMO evidence.
