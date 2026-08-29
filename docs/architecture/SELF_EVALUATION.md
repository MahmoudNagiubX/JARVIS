# Self-evaluation

`EvaluationService` runs local deterministic `EvaluationCase` instances in
named `RegressionSuite` collections. Default contract suites cover routing,
tool selection, permission decisions, memory/world-state retrieval, mission
planning, skill selection, citation quality, briefing relevance, and
proactive deduplication. Cases record expected and actual values, results,
summary, and whether a new failure is a regression from the last passing run.

No cloud grader or paid API is required. Evaluation results are durable and
exposed through the local API.
