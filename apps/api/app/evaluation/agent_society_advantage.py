from __future__ import annotations

from app.schemas.market import AgentSocietyAdvantageReport, BenchmarkMetrics


def compute_asai(
    benchmark_run_id: str, metrics: list[BenchmarkMetrics]
) -> AgentSocietyAdvantageReport:
    by_mode = {metric.mode: metric for metric in metrics}
    multi = by_mode["multi_agent"]
    single = by_mode["single_agent"]
    return_delta = multi.total_return_pct - single.total_return_pct
    violation_delta = single.risk_violations - multi.risk_violations
    quality_delta = multi.decision_quality - single.decision_quality
    accuracy_delta = multi.directional_accuracy - single.directional_accuracy
    score = (
        return_delta * 0.25
        + violation_delta * 8.0
        + quality_delta * 35.0
        + accuracy_delta * 25.0
        - max(0, multi.max_drawdown_pct - single.max_drawdown_pct) * 0.15
    )
    explanation = (
        "ASAI combines return delta, reduced risk violations, directional accuracy, "
        "decision quality, and drawdown penalty versus the single-agent baseline."
    )
    return AgentSocietyAdvantageReport(
        benchmark_run_id=benchmark_run_id,
        score=round(score, 3),
        metrics=metrics,
        explanation=explanation,
    )
