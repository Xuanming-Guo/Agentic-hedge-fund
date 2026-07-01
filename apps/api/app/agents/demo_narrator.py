from __future__ import annotations


class DemoNarratorAgent:
    def narrate(self, step: int) -> str:
        lines = [
            "The dashboard starts the synthetic market day.",
            "Qwen agents receive only point-in-time context.",
            "Tool calls fetch market, news, risk, and orderbook data.",
            "Bull and bear agents debate before the committee decides.",
            "Risk and compliance constraints govern execution.",
            "Benchmarks compare the society against baselines.",
        ]
        return lines[min(step, len(lines) - 1)]
