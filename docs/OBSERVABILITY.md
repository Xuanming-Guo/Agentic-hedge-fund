# Observability

The backend exposes structured JSON logs and `/metrics`.

Metrics include:

- `simulation_ticks_total`
- `agent_runs_total`
- `agent_failures_total`
- `llm_calls_total{provider}`
- `llm_latency_ms{provider}`
- `llm_tokens_total{provider}`
- `qwen_calls_total`
- `qwen_latency_ms`
- `qwen_tokens_total`
- `skill_calls_total`
- `skill_call_failures_total`
- `order_rejections_total`
- `risk_rejections_total`
- `compliance_rejections_total`
- `websocket_clients`
- `benchmark_runs_total`

The metrics are local and compatible with Prometheus scraping.
