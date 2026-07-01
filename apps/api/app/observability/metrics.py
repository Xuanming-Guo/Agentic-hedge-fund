from __future__ import annotations

try:
    from prometheus_client import Counter, Gauge, Histogram, generate_latest
except ModuleNotFoundError:  # pragma: no cover - local pre-install fallback

    class _Metric:
        def __init__(self, *_args, **_kwargs) -> None:
            self.value = 0

        def labels(self, **_kwargs):
            return self

        def inc(self, amount: int = 1) -> None:
            self.value += amount

        def dec(self, amount: int = 1) -> None:
            self.value -= amount

        def observe(self, _value: float) -> None:
            return None

    Counter = Gauge = Histogram = _Metric

    def generate_latest() -> bytes:
        return b"# prometheus_client not installed; fallback metrics active\n"


simulation_ticks_total = Counter("simulation_ticks_total", "Simulation ticks processed")
agent_runs_total = Counter("agent_runs_total", "Agent runs processed", ["agent"])
agent_failures_total = Counter("agent_failures_total", "Agent failures", ["agent"])
llm_calls_total = Counter("llm_calls_total", "LLM calls", ["provider"])
llm_latency_ms = Histogram("llm_latency_ms", "LLM latency in ms", ["provider"])
llm_tokens_total = Counter("llm_tokens_total", "LLM tokens", ["provider"])
qwen_calls_total = Counter("qwen_calls_total", "Qwen calls")
qwen_latency_ms = Histogram("qwen_latency_ms", "Qwen latency in ms")
qwen_tokens_total = Counter("qwen_tokens_total", "Qwen tokens")
skill_calls_total = Counter("skill_calls_total", "Skill calls", ["skill"])
skill_call_failures_total = Counter("skill_call_failures_total", "Skill call failures", ["skill"])
order_rejections_total = Counter("order_rejections_total", "Broker order rejections")
risk_rejections_total = Counter("risk_rejections_total", "Risk rejections")
compliance_rejections_total = Counter("compliance_rejections_total", "Compliance rejections")
websocket_clients = Gauge("websocket_clients", "Active websocket clients")
benchmark_runs_total = Counter("benchmark_runs_total", "Benchmark runs")


def render_metrics() -> bytes:
    return generate_latest()
