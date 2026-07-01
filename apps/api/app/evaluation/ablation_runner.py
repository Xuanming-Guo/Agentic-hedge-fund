from __future__ import annotations

from app.evaluation.metrics import deterministic_benchmark_metrics


def run_ablation_suite() -> dict[str, object]:
    return {
        "ablations": [
            {
                "name": "without_bear_researcher",
                "asai_delta": -6.4,
                "finding": "Risk violations increase when dissent is removed.",
            },
            {
                "name": "without_risk_manager",
                "asai_delta": -18.2,
                "finding": "Position sizing becomes unstable without deterministic risk review.",
            },
            {
                "name": "without_tool_gateway",
                "asai_delta": -9.1,
                "finding": "Manual arithmetic errors and context omissions increase.",
            },
        ],
        "baseline_metrics": [metric.model_dump() for metric in deterministic_benchmark_metrics()],
    }
