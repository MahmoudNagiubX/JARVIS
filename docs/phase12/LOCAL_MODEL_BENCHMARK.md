# Phase 12 local model benchmark

Physical run date: 2026-08-30, host `NIGHTFURY`.

Configuration was intentionally bounded for the constrained workstation:

- runtime: llama.cpp `0.3.0-dev`, build `10690`
- provider: `llama_cpp`
- model alias: `jarvis-local-qwen`
- context: 2,048
- CPU threads: 2
- GPU layers: 99
- endpoint: loopback only
- model size: 5,527,953,952 bytes

## Observed results

The real existing GGUF loaded in one product-owned server process. Health
reported `llama_cpp_ready` and the expected alias. Short bounded generation
returned visible English, Arabic-script, and mixed Arabic/English output
through `LlamaCppProvider`; observed latencies were approximately 1.5 s,
3.8 s, and 4.8 s respectively in the successful text run. No raw output or
prompt is retained here.

The standalone provider tool request for the harmless synthetic
`get_test_status` function produced one normalized call with a valid
dictionary argument. The real `AgentRuntime` text turn succeeded with model
id `jarvis-local-qwen` and did not return a mock response.

The bilingual closure keeps English visual intent at three visual schemas
(`desktop.context.read`, `screen.observe`, and `screen.latest`; 943 bytes),
while Arabic and mixed active-window metadata intent exposes the bounded
`desktop.context.read` schema only. Three fresh real Arabic `AgentRuntime`
desktop turns and one mixed Arabic/English turn each emitted
`desktop.context.read` followed by the complete tool lifecycle, then completed
a second model turn with a non-empty final response. The harmless Arabic
`status.read` turn also passed. The follow-up path omits duplicate grounding
context and bounds the structured tool evidence to 6,000 characters, keeping
the measured 2,048-token configuration usable.

The selector closure is conservative: it normalizes only its matching view,
does not alter stored user text, keeps ordinary Arabic and English chat
tool-free, rejects the `what type of ...` keyboard false positive, and never
uses tool output to expand a second-turn schema selection. The focused closure
matrix passed 45/0; the full repository suite passed 218/0.

The strict model identity check requires the configured alias in `/v1/models`;
vision is reported as `model_route_unsupported`, and local generation is
serialized with one active request plus eight bounded waiters. No `tool_choice`
flag was added because schema filtering was sufficient, and no regex/free-text
tool parser was introduced.

After the owned server was stopped, an AgentRuntime request failed with the
normalized offline provider error. Restarting the same supervisor restored
`ready`. The owned process was stopped during cleanup and no second model
server was used. A 4,096-token comparison was skipped because the available
workstation memory did not make a safe comparison appropriate.
