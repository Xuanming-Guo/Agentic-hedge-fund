import { Gauge } from 'lucide-react';
import type { BenchmarkReport, ReplayBenchmarkRun } from '../../lib/types';

type Props = {
  benchmark: BenchmarkReport | null;
  onRun: () => void;
  replayBenchmark?: ReplayBenchmarkRun | null;
  className?: string;
};

function pct(value: number) {
  return `${Math.round(value * 100)}%`;
}

function delta(value: number) {
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}`;
}

function replaySparklinePoints(run: ReplayBenchmarkRun) {
  if (run.items.length === 0) return '';
  if (run.items.length === 1) return '0,18 100,18';
  const scores = run.items.map((item) => item.benchmark.score);
  const min = Math.min(...scores);
  const max = Math.max(...scores);
  const spread = Math.max(0.001, max - min);
  return scores
    .map((score, index) => {
      const x = (index / Math.max(1, scores.length - 1)) * 100;
      const y = 34 - ((score - min) / spread) * 28;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(' ');
}

function metricRows(
  multi: NonNullable<BenchmarkReport['metrics'][number]>,
  single: NonNullable<BenchmarkReport['metrics'][number]>
) {
  return [
    ['Return', `${multi.total_return_pct.toFixed(2)}%`, `${single.total_return_pct.toFixed(2)}%`],
    ['Max drawdown', `${multi.max_drawdown_pct.toFixed(2)}%`, `${single.max_drawdown_pct.toFixed(2)}%`],
    ['Risk violations', String(multi.risk_violations), String(single.risk_violations)],
    ['Directional accuracy', pct(multi.directional_accuracy), pct(single.directional_accuracy)],
    ['Decision quality', pct(multi.decision_quality), pct(single.decision_quality)]
  ];
}

export function BenchmarkCard({
  benchmark,
  onRun,
  replayBenchmark = null,
  className = 'span-6'
}: Props) {
  const multi = benchmark?.metrics.find((metric) => metric.mode === 'multi_agent');
  const single = benchmark?.metrics.find((metric) => metric.mode === 'single_agent');
  const hasReplayTimeline = Boolean(replayBenchmark?.items.length);
  return (
    <section className={`panel ${className}`}>
      <h2>Agent Society Benchmark</h2>
      <div className="panel-body benchmark-card">
        <div>
          <p className="muted">
            Measures the multi-agent society against a single-agent baseline using return,
            drawdown, evidence-backed decisions, and risk/compliance outcomes.
          </p>
          <button className="btn warning" onClick={onRun}>
            <Gauge size={15} />
            Run benchmark
          </button>
        </div>
        <div className="benchmark-output">
          {hasReplayTimeline && replayBenchmark ? (
            <div className="benchmark-timeline" aria-label="Replay benchmark timeline">
              <div>
                <span className="badge green">Replay keyframe benchmark</span>
                <strong>{replayBenchmark.items.length} keyframes</strong>
                <span className="muted">
                  latest ASAI {replayBenchmark.summary?.score.toFixed(2) ?? 'n/a'}
                </span>
              </div>
              <svg viewBox="0 0 100 40" role="img" aria-label="ASAI over replay keyframes">
                <line x1="0" x2="100" y1="34" y2="34" />
                <polyline points={replaySparklinePoints(replayBenchmark)} />
              </svg>
            </div>
          ) : null}
          {benchmark && multi && single ? (
            <div className="benchmark-proof">
              <div className="benchmark-proof-header">
                <span className="badge green">Agent Society baseline proof</span>
                <div className="benchmark-summary">
                  <div>
                    <span className="muted">ASAI score</span>
                    <strong>{benchmark.score.toFixed(2)}</strong>
                  </div>
                  <div>
                    <span className="muted">Return delta</span>
                    <strong>{delta(multi.total_return_pct - single.total_return_pct)} pts</strong>
                  </div>
                  <div>
                    <span className="muted">Risk avoided</span>
                    <strong>{Math.max(0, single.risk_violations - multi.risk_violations)}</strong>
                  </div>
                </div>
              </div>
              <div className="benchmark-compare" role="table" aria-label="multi_agent vs single_agent benchmark">
                <div className="benchmark-compare-row benchmark-compare-head" role="row">
                  <span role="columnheader">Metric</span>
                  <strong role="columnheader">multi_agent</strong>
                  <strong role="columnheader">single_agent</strong>
                </div>
                {metricRows(multi, single).map(([label, multiValue, singleValue]) => (
                  <div className="benchmark-compare-row" role="row" key={label}>
                    <span role="cell">{label}</span>
                    <strong role="cell">{multiValue}</strong>
                    <span role="cell">{singleValue}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="empty-chart compact">
              <strong>No benchmark yet</strong>
              <span className="muted">Run benchmark to compare multi_agent vs single_agent.</span>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
