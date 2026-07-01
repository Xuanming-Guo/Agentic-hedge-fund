import { render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import type { BenchmarkReport, ReplayBenchmarkRun } from '../../lib/types';
import { BenchmarkCard } from './BenchmarkCard';

const benchmark: BenchmarkReport = {
  benchmark_run_id: 'bench-test',
  score: 0.73,
  explanation: 'Agent society improves decision quality versus the single-agent baseline.',
  metrics: [
    {
      mode: 'multi_agent',
      total_return_pct: 1.82,
      max_drawdown_pct: 0.74,
      sharpe_like: 1.31,
      risk_violations: 0,
      compliance_rejections: 1,
      directional_accuracy: 0.68,
      decision_quality: 0.81,
      token_usage: 9200
    },
    {
      mode: 'single_agent',
      total_return_pct: 1.21,
      max_drawdown_pct: 1.42,
      sharpe_like: 0.72,
      risk_violations: 3,
      compliance_rejections: 0,
      directional_accuracy: 0.57,
      decision_quality: 0.62,
      token_usage: 4100
    }
  ]
};

const replayBenchmark: ReplayBenchmarkRun = {
  recording_id: 'rec-demo',
  scope: 'keyframes',
  summary: { ...benchmark, benchmark_run_id: 'bench-later', score: 1.08 },
  items: [
    {
      frame_index: 0,
      event_index: 0,
      reason: 'Initial frame',
      timestamp: '2026-06-30T14:30:00Z',
      benchmark
    },
    {
      frame_index: 8,
      event_index: 1,
      reason: 'Benchmark update',
      timestamp: '2026-06-30T14:45:00Z',
      benchmark: { ...benchmark, benchmark_run_id: 'bench-later', score: 1.08 }
    }
  ]
};

test('makes the multi-agent versus single-agent baseline proof visible', () => {
  render(<BenchmarkCard benchmark={benchmark} onRun={vi.fn()} />);

  expect(screen.getByText('Agent Society baseline proof')).toBeInTheDocument();
  expect(screen.getByText('multi_agent')).toBeInTheDocument();
  expect(screen.getByText('single_agent')).toBeInTheDocument();
  expect(screen.getByText('ASAI score')).toBeInTheDocument();
  expect(screen.getByText('+0.61 pts')).toBeInTheDocument();
  expect(screen.queryByText('Token usage')).not.toBeInTheDocument();
});

test('shows replay keyframe benchmark coverage', () => {
  render(<BenchmarkCard benchmark={benchmark} onRun={vi.fn()} replayBenchmark={replayBenchmark} />);

  expect(screen.getByText('Replay keyframe benchmark')).toBeInTheDocument();
  expect(screen.getByText('2 keyframes')).toBeInTheDocument();
  expect(screen.getByText('latest ASAI 1.08')).toBeInTheDocument();
  expect(screen.getByRole('img', { name: /ASAI over replay keyframes/i })).toBeInTheDocument();
});

test('empty state names the required baseline comparison', () => {
  render(<BenchmarkCard benchmark={null} onRun={vi.fn()} />);

  expect(screen.getByText('Run benchmark to compare multi_agent vs single_agent.')).toBeInTheDocument();
});
