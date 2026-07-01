# Benchmarking

Benchmark modes:

- Multi-agent society.
- Single Qwen baseline agent.
- Rule-based baseline.
- Buy-and-hold baseline.
- Seeded random/noise trader baseline.

Metrics:

- Total return.
- Max drawdown.
- Sharpe-like score.
- Risk violations.
- Compliance rejections.
- Directional accuracy.
- Decision quality.

## Agent Society Advantage Index

ASAI combines return delta, reduced risk violations, directional accuracy, decision quality, and drawdown penalty versus the single-agent baseline.

Implementation: `apps/api/app/evaluation/agent_society_advantage.py`.

The multi-agent row is derived from the current simulation state: open/realized PnL, committee decisions,
evidence coverage, risk conflicts, and compliance rejections. Baseline rows are deterministic
comparators so reviewers can rerun the same scenario and get stable ASAI comparisons. No future returns are exposed
to agents before the clock advances.
