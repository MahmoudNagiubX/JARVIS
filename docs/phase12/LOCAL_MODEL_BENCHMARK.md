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

The real `AgentRuntime` desktop-context request did not emit a tool call or a
`tool.completed` event; it returned an empty assistant turn. This is recorded
as `agent_tool_call=PARTIAL`, so Phase 12 is not claimed as a full live-agent
PASS. No regex or text heuristic was used to promote it.

After the owned server was stopped, an AgentRuntime request failed with the
normalized offline provider error. Restarting the same supervisor restored
`ready`. The owned process was stopped during cleanup and no second model
server was used.
