import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { DashboardPage } from './DashboardPage';
import type { BenchmarkReport, SimulationSnapshot } from '../lib/types';

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;

  constructor() {
    MockWebSocket.instances.push(this);
    window.setTimeout(() => this.onopen?.(), 0);
  }

  close() {
    this.onclose?.();
  }
}

const snapshot: SimulationSnapshot = {
  simulation_id: 'sim-workspace',
  scenario: {
    id: '2024-05-10',
    display_date: '2024-05-10',
    title: 'Workspace test',
    description: 'Workspace test',
    seed: 1,
    status: 'active'
  },
  instruments: [{ symbol: 'ALPH', display_name: 'Alpha Systems', sector: 'Technology', tick_size: 0.01, lot_size: 1, starting_price: 120 }],
  market_data: {
    mode: 'synthetic',
    provider: 'synthetic',
    feed: 'synthetic',
    is_delayed: false,
    quote_source: 'synthetic',
    depth_source: 'synthetic_limit_order_book',
    requested_tickers: [],
    active_tickers: [],
    replay_date: null,
    warning: null
  },
  status: 'running',
  current_time: '2026-06-30T14:30:00Z',
  speed: 1,
  released_events: [],
  latest_bars: [],
  history_bars: [],
  orderbooks: [],
  trade_tape: [],
  portfolio: {
    cash: 1_000_000,
    equity: 1_000_000,
    realized_pnl: 0,
    unrealized_pnl: 0,
    gross_exposure: 0,
    net_exposure: 0,
    sector_exposure: {},
    positions: []
  },
  portfolio_history: [],
  candidate_slate: [],
  agent_states: [],
  debate: [],
  conflicts: [],
  agent_decisions: [],
  committee_decisions: [],
  consensus: [],
  skill_calls: [],
  agent_activity_feed: [],
  benchmark: null,
  agent_cycle_status: 'idle',
  active_cycle_id: null,
  active_agent: null,
  active_provider: 'qwen',
  configured_provider: 'qwen',
  completed_llm_calls: 0,
  expected_llm_calls: 6,
  last_llm_error: null,
  last_llm_provider: null,
  last_completed_provider: null,
  last_fallback_provider: null,
  last_fallback_agent: null,
  last_fallback_reason: null,
  last_llm_model: null,
  last_llm_calls: 0,
  last_llm_tokens: 0
};

function benchmark(score: number, returnPct = 1.2): BenchmarkReport {
  return {
    benchmark_run_id: `bench-${score}`,
    score,
    explanation: 'ASAI compares the multi-agent society with the single-agent baseline.',
    metrics: [
      {
        mode: 'multi_agent',
        total_return_pct: returnPct,
        max_drawdown_pct: 0.5,
        sharpe_like: 1.2,
        risk_violations: 0,
        compliance_rejections: 0,
        directional_accuracy: 0.7,
        decision_quality: 0.8,
        token_usage: 9000
      },
      {
        mode: 'single_agent',
        total_return_pct: returnPct - 0.4,
        max_drawdown_pct: 1.1,
        sharpe_like: 0.7,
        risk_violations: 2,
        compliance_rejections: 0,
        directional_accuracy: 0.58,
        decision_quality: 0.62,
        token_usage: 4200
      }
    ]
  };
}

beforeEach(() => {
  window.localStorage.clear();
  MockWebSocket.instances = [];
  vi.stubGlobal('WebSocket', MockWebSocket);
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/api/scenarios')) {
        return Response.json({ scenarios: [snapshot.scenario] });
      }
      if (url.includes('/api/recordings')) {
        return Response.json({ recordings: [] });
      }
      if (url.includes('/api/simulations/estimate')) {
        return Response.json({ estimated_real_seconds: 8, warning: null });
      }
      if (url.includes('/api/simulations/recorded')) {
        return Response.json({
          recording: {
            recording_id: 'rec-workspace',
            simulation_id: 'sim-workspace',
            name: 'Workspace recording',
            scenario_id: '2024-05-10',
            scenario_title: 'Workspace test',
            status: 'running',
            duration_minutes: 60,
            simulated_start: '2026-06-30T14:30:00Z',
            simulated_end: null,
            created_at: '2026-06-30T14:30:00Z',
            updated_at: '2026-06-30T14:30:00Z',
            frame_count: 1,
            event_count: 0,
            last_frame_index: 0,
            can_continue: true,
            market_data_mode: 'synthetic',
            tickers: [],
            summary: 'Recording live simulation frames for exact replay.'
          },
          snapshot
        });
      }
      return Response.json({});
    })
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function enabledCreateRecordingButton() {
  const button = await screen.findByRole('button', { name: /Create recording/i });
  await waitFor(() => expect(button).toBeEnabled());
  return button;
}

test('launcher explains backend startup failures instead of showing empty lists', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/api/scenarios') || url.includes('/api/recordings')) {
        return Response.json({ detail: 'connection refused' }, { status: 503, statusText: 'Unavailable' });
      }
      if (url.includes('/api/simulations/estimate')) {
        return Response.json({ estimated_real_seconds: 8, warning: null });
      }
      return Response.json({});
    })
  );

  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <DashboardPage />
    </QueryClientProvider>
  );

  expect(await screen.findByText('Scenarios unavailable')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Create recording/i })).toBeDisabled();
  const hints = await screen.findAllByText(/docker compose logs api postgres/i);
  expect(hints).toHaveLength(2);
});

test('live dashboard defaults to core trading panels plus agent society live', async () => {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <DashboardPage />
    </QueryClientProvider>
  );

  fireEvent.click(await enabledCreateRecordingButton());

  expect(await screen.findByRole('heading', { name: 'Market Replay Candles' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Order Book' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Agent Society Live' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Portfolio' })).toBeInTheDocument();
  expect(screen.queryByRole('heading', { name: 'Agent Runtime' })).not.toBeInTheDocument();
  expect(screen.queryByRole('heading', { name: 'Investment Committee' })).not.toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Agent Society Live' }).closest('.dock-panel')).toHaveClass(
    'span-4',
    'row-span-1'
  );
  expect(screen.getByRole('heading', { name: 'Portfolio' }).closest('.dock-panel')).toHaveClass(
    'span-4',
    'row-span-1'
  );
  expect(screen.queryByText(/qwen|qwen-plus|mock/i)).not.toBeInTheDocument();
});

test('shows a simple spinner while create recording is pending', async () => {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <DashboardPage />
    </QueryClientProvider>
  );

  const createButton = await enabledCreateRecordingButton();
  let resolveCreate = (response: Response) => {
    void response;
  };
  const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
  fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes('/api/simulations/recorded')) {
      return new Promise<Response>((resolve) => {
        resolveCreate = resolve;
      });
    }
    if (url.includes('/api/scenarios')) {
      return Response.json({ scenarios: [snapshot.scenario] });
    }
    if (url.includes('/api/recordings')) {
      return Response.json({ recordings: [] });
    }
    if (url.includes('/api/simulations/estimate')) {
      return Response.json({ estimated_real_seconds: 8, warning: null });
    }
    return Response.json({});
  });

  fireEvent.click(createButton);

  expect(await screen.findByRole('status')).toHaveTextContent('Creating recorded simulation');
  expect(document.querySelector('.terminal-spinner')).not.toBeNull();
  expect(document.querySelector('.terminal-loader-grid')).toBeNull();
  expect(document.querySelector('.terminal-loader-bars')).toBeNull();

  resolveCreate(
    Response.json({
      recording: {
        recording_id: 'rec-workspace',
        simulation_id: 'sim-workspace',
        name: 'Workspace recording',
        scenario_id: '2024-05-10',
        scenario_title: 'Workspace test',
        status: 'running',
        duration_minutes: 60,
        simulated_start: '2026-06-30T14:30:00Z',
        simulated_end: null,
        created_at: '2026-06-30T14:30:00Z',
        updated_at: '2026-06-30T14:30:00Z',
        frame_count: 1,
        event_count: 0,
        last_frame_index: 0,
        can_continue: true,
        market_data_mode: 'synthetic',
        tickers: [],
        summary: 'Recording live simulation frames for exact replay.'
      },
      snapshot
    })
  );

  await waitFor(() => expect(screen.queryByRole('status')).not.toBeInTheDocument());
});

test('reconnects the live socket after an unexpected close', async () => {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <DashboardPage />
    </QueryClientProvider>
  );

  fireEvent.click(await enabledCreateRecordingButton());

  expect(await screen.findByText('connected')).toBeInTheDocument();

  MockWebSocket.instances[0].onclose?.();

  expect(await screen.findByText('reconnecting')).toBeInTheDocument();
  await waitFor(() => expect(MockWebSocket.instances.length).toBeGreaterThan(1));
  expect(await screen.findByText('connected')).toBeInTheDocument();
});

test('shows a readable error when a saved replay cannot be loaded', async () => {
  const detail = 'Saved replay file is corrupted and cannot be loaded.';
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/api/scenarios')) {
        return Response.json({ scenarios: [snapshot.scenario] });
      }
      if (url.includes('/api/recordings/rec-corrupt/keyframes')) {
        return Response.json({ detail }, { status: 409, statusText: 'Conflict' });
      }
      if (url.includes('/api/recordings')) {
        return Response.json({
          recordings: [
            {
              recording_id: 'rec-corrupt',
              simulation_id: 'sim-workspace',
              name: 'Broken replay',
              scenario_id: '2024-05-10',
              scenario_title: 'Workspace test',
              status: 'incomplete',
              duration_minutes: 60,
              simulated_start: '2026-06-30T14:30:00Z',
              simulated_end: null,
              created_at: '2026-06-30T14:30:00Z',
              updated_at: '2026-06-30T14:30:00Z',
              frame_count: 1,
              event_count: 0,
              last_frame_index: 0,
              can_continue: true,
              market_data_mode: 'synthetic',
              tickers: [],
              summary: 'Stopped early.'
            }
          ]
        });
      }
      if (url.includes('/api/simulations/estimate')) {
        return Response.json({ estimated_real_seconds: 8, warning: null });
      }
      return Response.json({});
    })
  );

  render(
    <QueryClientProvider client={new QueryClient()}>
      <DashboardPage />
    </QueryClientProvider>
  );

  await screen.findByText('Broken replay');
  fireEvent.click(screen.getByRole('button', { name: /Replay/i }));

  expect(await screen.findByRole('alert')).toHaveTextContent(detail);
});

test('shows progress while saved replay keyframes load', async () => {
  const firstFrame = {
    index: 0,
    timestamp: '2026-06-30T14:30:00Z',
    elapsed_sim_minutes: 0,
    snapshot
  };
  let resolveKeyframes = (response: Response) => {
    void response;
  };
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/api/scenarios')) {
        return Response.json({ scenarios: [snapshot.scenario] });
      }
      if (url.includes('/api/recordings/rec-progress/keyframes')) {
        return new Promise<Response>((resolve) => {
          resolveKeyframes = resolve;
        });
      }
      if (url.includes('/api/recordings')) {
        return Response.json({
          recordings: [
            {
              recording_id: 'rec-progress',
              simulation_id: 'sim-workspace',
              name: 'Progress replay',
              scenario_id: '2024-05-10',
              scenario_title: 'Workspace test',
              status: 'complete',
              duration_minutes: 390,
              simulated_start: '2026-06-30T14:30:00Z',
              simulated_end: '2026-06-30T14:31:00Z',
              created_at: '2026-06-30T14:30:00Z',
              updated_at: '2026-06-30T14:31:00Z',
              frame_count: 1,
              event_count: 0,
              last_frame_index: 0,
              can_continue: false,
              market_data_mode: 'synthetic',
              tickers: [],
              summary: 'Completed recorded simulation.'
            }
          ]
        });
      }
      if (url.includes('/api/simulations/estimate')) {
        return Response.json({ estimated_real_seconds: 8, warning: null });
      }
      return Response.json({});
    })
  );

  render(
    <QueryClientProvider client={new QueryClient()}>
      <DashboardPage />
    </QueryClientProvider>
  );

  await screen.findByText('Progress replay');
  fireEvent.click(screen.getByRole('button', { name: /Replay/i }));

  expect(await screen.findByRole('status')).toHaveTextContent('Loading action replay');
  expect(screen.getByRole('progressbar', { name: /Replay loading progress/i })).toBeInTheDocument();
  expect(screen.getByText('Preparing replay timeline')).toBeInTheDocument();

  resolveKeyframes(
    Response.json({
      keyframes: [
        {
          frame_index: 0,
          event_index: 0,
          reason: 'Initial frame',
          frame: firstFrame
        }
      ]
    })
  );

  await waitFor(() => expect(screen.queryByRole('status')).not.toBeInTheDocument());
});

test('opens saved replay from keyframes and loads full frames lazily', async () => {
  const calls: string[] = [];
  const firstFrame = {
    index: 0,
    timestamp: '2026-06-30T14:30:00Z',
    elapsed_sim_minutes: 0,
    snapshot
  };
  const secondFrame = {
    index: 1,
    timestamp: '2026-06-30T14:31:00Z',
    elapsed_sim_minutes: 1,
    snapshot: { ...snapshot, current_time: '2026-06-30T14:31:00Z' }
  };
  let resolveFrames = (response: Response) => {
    void response;
  };
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      calls.push(url);
      if (url.includes('/api/scenarios')) {
        return Response.json({ scenarios: [snapshot.scenario] });
      }
      if (url.includes('/api/recordings/rec-fast/keyframes')) {
        return Response.json({
          keyframes: [
            {
              frame_index: 0,
              event_index: 0,
              reason: 'Initial frame',
              frame: firstFrame
            }
          ]
        });
      }
      if (url.includes('/api/recordings/rec-fast/frames')) {
        return new Promise<Response>((resolve) => {
          resolveFrames = resolve;
        });
      }
      if (url.includes('/api/recordings')) {
        return Response.json({
          recordings: [
            {
              recording_id: 'rec-fast',
              simulation_id: 'sim-workspace',
              name: 'Full day replay',
              scenario_id: '2024-05-10',
              scenario_title: 'Workspace test',
              status: 'complete',
              duration_minutes: 390,
              simulated_start: '2026-06-30T14:30:00Z',
              simulated_end: '2026-06-30T14:31:00Z',
              created_at: '2026-06-30T14:30:00Z',
              updated_at: '2026-06-30T14:31:00Z',
              frame_count: 2,
              event_count: 0,
              last_frame_index: 1,
              can_continue: false,
              market_data_mode: 'synthetic',
              tickers: [],
              summary: 'Completed recorded simulation.'
            }
          ]
        });
      }
      if (url.includes('/api/simulations/estimate')) {
        return Response.json({ estimated_real_seconds: 8, warning: null });
      }
      return Response.json({});
    })
  );

  render(
    <QueryClientProvider client={new QueryClient()}>
      <DashboardPage />
    </QueryClientProvider>
  );

  await screen.findByText('Full day replay');
  fireEvent.click(screen.getByRole('button', { name: /Replay/i }));

  expect(await screen.findByText('saved replay')).toBeInTheDocument();
  expect(calls.some((url) => url.includes('/api/recordings/rec-fast/keyframes'))).toBe(true);
  expect(calls.some((url) => url.includes('/api/recordings/rec-fast/frames'))).toBe(false);

  fireEvent.click(screen.getByRole('button', { name: /Full frames/i }));

  expect(await screen.findByRole('status')).toHaveTextContent('Loading raw replay frames');
  expect(screen.getByRole('progressbar', { name: /Replay loading progress/i })).toHaveValue(0);

  resolveFrames(Response.json({ frames: [firstFrame, secondFrame] }));

  await waitFor(() =>
    expect(calls.some((url) => url.includes('/api/recordings/rec-fast/frames'))).toBe(true)
  );
  expect(await screen.findByText('frame 1/2')).toBeInTheDocument();
});

test('runs replay benchmark over keyframes and overlays the current replay point', async () => {
  const calls: string[] = [];
  const firstFrame = {
    index: 0,
    timestamp: '2026-06-30T14:30:00Z',
    elapsed_sim_minutes: 0,
    snapshot
  };
  const secondFrame = {
    index: 7,
    timestamp: '2026-06-30T14:45:00Z',
    elapsed_sim_minutes: 15,
    snapshot: { ...snapshot, current_time: '2026-06-30T14:45:00Z' }
  };
  const firstBenchmark = benchmark(1.11);
  const secondBenchmark = benchmark(2.22);
  let resolveBenchmark = (response: Response) => {
    void response;
  };
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      calls.push(url);
      if (url.includes('/api/scenarios')) {
        return Response.json({ scenarios: [snapshot.scenario] });
      }
      if (url.includes('/api/recordings/rec-benchmark/benchmark')) {
        return new Promise<Response>((resolve) => {
          resolveBenchmark = resolve;
        });
      }
      if (url.includes('/api/recordings/rec-benchmark/keyframes')) {
        return Response.json({
          keyframes: [
            {
              frame_index: 0,
              event_index: 0,
              reason: 'Initial frame',
              frame: firstFrame
            },
            {
              frame_index: 7,
              event_index: 1,
              reason: 'Final frame',
              frame: secondFrame
            }
          ]
        });
      }
      if (url.includes('/api/recordings')) {
        return Response.json({
          recordings: [
            {
              recording_id: 'rec-benchmark',
              simulation_id: 'sim-workspace',
              name: 'Benchmark replay',
              scenario_id: '2024-05-10',
              scenario_title: 'Workspace test',
              status: 'complete',
              duration_minutes: 390,
              simulated_start: '2026-06-30T14:30:00Z',
              simulated_end: '2026-06-30T14:45:00Z',
              created_at: '2026-06-30T14:30:00Z',
              updated_at: '2026-06-30T14:45:00Z',
              frame_count: 8,
              event_count: 0,
              last_frame_index: 7,
              can_continue: false,
              market_data_mode: 'synthetic',
              tickers: [],
              summary: 'Completed recorded simulation.'
            }
          ]
        });
      }
      if (url.includes('/api/simulations/estimate')) {
        return Response.json({ estimated_real_seconds: 8, warning: null });
      }
      return Response.json({});
    })
  );

  render(
    <QueryClientProvider client={new QueryClient()}>
      <DashboardPage />
    </QueryClientProvider>
  );

  await screen.findByText('Benchmark replay');
  fireEvent.click(screen.getByRole('button', { name: /Replay/i }));
  expect(await screen.findByText('saved replay')).toBeInTheDocument();

  fireEvent.click(screen.getByText('Add Panel'));
  fireEvent.click(screen.getByRole('button', { name: /Agent Society Benchmark/i }));
  fireEvent.click(screen.getByRole('button', { name: /Run benchmark/i }));

  expect(await screen.findByRole('status')).toHaveTextContent('Benchmarking replay keyframes');
  expect(screen.getByRole('progressbar', { name: /Replay loading progress/i })).toBeInTheDocument();

  resolveBenchmark(
    Response.json({
      recording_id: 'rec-benchmark',
      scope: 'keyframes',
      summary: secondBenchmark,
      items: [
        {
          frame_index: 0,
          event_index: 0,
          reason: 'Initial frame',
          timestamp: firstFrame.timestamp,
          benchmark: firstBenchmark
        },
        {
          frame_index: 7,
          event_index: 1,
          reason: 'Final frame',
          timestamp: secondFrame.timestamp,
          benchmark: secondBenchmark
        }
      ]
    })
  );

  expect(await screen.findByText('Replay keyframe benchmark')).toBeInTheDocument();
  expect(screen.getByText('2 keyframes')).toBeInTheDocument();
  expect(calls.some((url) => url.includes('/api/recordings/rec-benchmark/benchmark'))).toBe(true);

  await waitFor(() => {
    expect(document.querySelector('.benchmark-summary')).toHaveTextContent('1.11');
  });

  fireEvent.change(screen.getByLabelText('Replay event'), { target: { value: '1' } });

  await waitFor(() => {
    expect(document.querySelector('.benchmark-summary')).toHaveTextContent('2.22');
  });
});
