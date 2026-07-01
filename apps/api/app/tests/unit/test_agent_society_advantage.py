from __future__ import annotations

from app.evaluation.agent_society_advantage import compute_asai
from app.evaluation.metrics import deterministic_benchmark_metrics


def test_asai_rewards_lower_risk_violations() -> None:
    report = compute_asai("bench", deterministic_benchmark_metrics())
    assert report.score > 0
    assert report.metrics[0].mode == "multi_agent"
