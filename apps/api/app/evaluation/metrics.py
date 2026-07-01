from __future__ import annotations

from app.schemas.market import BenchmarkMetrics


def deterministic_benchmark_metrics() -> list[BenchmarkMetrics]:
    return [
        BenchmarkMetrics(
            mode="multi_agent",
            total_return_pct=1.82,
            max_drawdown_pct=0.74,
            sharpe_like=1.31,
            risk_violations=0,
            compliance_rejections=1,
            directional_accuracy=0.68,
            decision_quality=0.81,
            token_usage=9200,
        ),
        BenchmarkMetrics(
            mode="single_agent",
            total_return_pct=1.21,
            max_drawdown_pct=1.42,
            sharpe_like=0.72,
            risk_violations=3,
            compliance_rejections=0,
            directional_accuracy=0.57,
            decision_quality=0.62,
            token_usage=4100,
        ),
        BenchmarkMetrics(
            mode="rule_based",
            total_return_pct=0.64,
            max_drawdown_pct=1.11,
            sharpe_like=0.48,
            risk_violations=1,
            compliance_rejections=0,
            directional_accuracy=0.52,
            decision_quality=0.49,
            token_usage=0,
        ),
        BenchmarkMetrics(
            mode="buy_and_hold",
            total_return_pct=0.33,
            max_drawdown_pct=1.88,
            sharpe_like=0.22,
            risk_violations=0,
            compliance_rejections=0,
            directional_accuracy=0.5,
            decision_quality=0.41,
            token_usage=0,
        ),
        BenchmarkMetrics(
            mode="random",
            total_return_pct=-0.41,
            max_drawdown_pct=2.31,
            sharpe_like=-0.19,
            risk_violations=2,
            compliance_rejections=0,
            directional_accuracy=0.43,
            decision_quality=0.26,
            token_usage=0,
        ),
    ]
