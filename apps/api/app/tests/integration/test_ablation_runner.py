from __future__ import annotations

from app.evaluation.ablation_runner import run_ablation_suite


def test_ablation_runner_returns_findings() -> None:
    result = run_ablation_suite()
    assert result["ablations"]
