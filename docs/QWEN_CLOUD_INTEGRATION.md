# Qwen Cloud Integration

Agentic Hedge Fund uses Qwen Cloud as its only real model provider. The backend falls back to deterministic mock agents only when `DASHSCOPE_API_KEY` is not configured, which keeps tests and offline demos reproducible.

## Runtime Modes

- `QwenCloudProvider`: OpenAI-compatible DashScope/Qwen client for structured JSON agent calls.
- `MockLLMProvider`: deterministic offline/test fallback. It is not treated as a real model provider.

Provider resolution:

1. `DASHSCOPE_API_KEY` present: use Qwen Cloud.
2. No Qwen key: use deterministic mock fallback.

## Environment

```bash
DASHSCOPE_API_KEY=
QWEN_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
QWEN_MODEL_REASONING=qwen3.7-plus
QWEN_MODEL_FAST=qwen3.7-flash
QWEN_MODEL_CODER=qwen3-coder-plus
QWEN_JSON_MODE=true
QWEN_STRUCTURED_OUTPUT_STRATEGY=json_object
QWEN_ENABLE_THINKING=false
MAX_QWEN_CALLS_PER_CYCLE=12
MAX_QWEN_TOOL_CALLS_PER_AGENT=6
MAX_PARALLEL_AGENT_CALLS=5
```

## Structured Output

- Every agent call requests structured JSON when configured.
- Pydantic validation is mandatory before output can influence a simulated order.
- A repair prompt is attempted once on schema failure.
- Invalid or unsafe output falls back to no-trade or deterministic mock fallback behavior, depending on the failure point.
- Secrets are never sent to the frontend and are redacted from saved recordings.

## Proof

Proof endpoint:

```text
GET /api/proof/qwen
```

It reports whether Qwen is configured, whether structured JSON mode is enabled, whether tool and MCP paths are available, and recent call/tool counters. It does not expose secret values or model/provider names in saved replay payloads.
