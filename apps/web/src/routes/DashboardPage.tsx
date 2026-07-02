import { useEffect, useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Activity,
  Archive,
  BrainCircuit,
  Pause,
  Play,
  RotateCcw,
  Save,
  SkipForward,
  StepForward
} from 'lucide-react';
import {
  controlSimulation,
  createRecordedSimulation,
  estimateSimulation,
  getRecordingActivityDetail,
  getRecordingFrames,
  getRecordingKeyframes,
  listRecordings,
  listScenarios,
  resumeRecording,
  runRecordingBenchmark,
  runSimulationBenchmark,
  setSpeed,
  stopAndSaveSimulation
} from '../lib/api';
import {
  frameAtTimelineIndex,
  replayDelayForSpeed,
  timelineLength,
  type ReplayKeyframe,
  type ReplayTimelineMode
} from '../lib/replayTimeline';
import { useSimulationSocket } from '../lib/useSimulationSocket';
import type {
  RecordingManifest,
  ReplayBenchmarkRun,
  SimulationRecordingFrame,
  SimulationSnapshot
} from '../lib/types';
import { AgentDecisionFlow } from '../components/dashboard/AgentDecisionFlow';
import { AgentSocietyLive } from '../components/dashboard/AgentSocietyLive';
import { AgentWorkbench } from '../components/dashboard/AgentWorkbench';
import { BenchmarkCard } from '../components/dashboard/BenchmarkCard';
import { CandlestickChart } from '../components/dashboard/CandlestickChart';
import { CandidateSlatePanel } from '../components/dashboard/CandidateSlatePanel';
import { DockableWorkspace, type WorkspacePanel } from '../components/dashboard/DockableWorkspace';
import { HumanApprovalModal } from '../components/dashboard/HumanApprovalModal';
import { InvestmentCommitteeBoard } from '../components/dashboard/InvestmentCommitteeBoard';
import { OrderBookPanel } from '../components/dashboard/OrderBookPanel';
import { PortfolioPanel } from '../components/dashboard/PortfolioPanel';

const liveSpeeds = [1, 5, 20];
const replaySpeeds = [1, 5, 20];
const durationOptions = [30, 60, 120, 390];

type DashboardMode = 'launcher' | 'live' | 'replay';
type MarketDataMode = 'synthetic' | 'yfinance' | 'alpaca';

function formatTime(seconds: number) {
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return remainder ? `${minutes}m ${remainder}s` : `${minutes}m`;
}

function agentProgressRatio(snapshot: SimulationSnapshot) {
  const expected = Math.max(1, snapshot.expected_llm_calls ?? 0);
  return Math.min(1, (snapshot.completed_llm_calls ?? 0) / expected);
}

function agentEmptyReason(snapshot: SimulationSnapshot) {
  if (snapshot.agent_cycle_status === 'running') {
    return `${snapshot.active_agent ?? 'Agent'} is calling the AI runtime. Decisions appear when this cycle completes.`;
  }
  const hasTrace =
    snapshot.agent_states.length > 0 ||
    snapshot.agent_decisions.length > 0 ||
    snapshot.debate.length > 0 ||
    snapshot.skill_calls.length > 0;
  if ((snapshot.last_llm_calls ?? 0) === 0 && hasTrace) {
    return 'A deterministic trace is available. Live AI activity appears during the next agent cycle.';
  }
  if (snapshot.status === 'running') return 'Waiting for next agent cycle.';
  return 'Start or replay a recorded simulation to inspect the agent society.';
}

function benchmarkForReplayFrame(run: ReplayBenchmarkRun | null, frameIndex: number | null) {
  if (!run || frameIndex === null || run.items.length === 0) return null;
  let candidate = run.items[0];
  for (const item of run.items) {
    if (item.frame_index > frameIndex) break;
    candidate = item;
  }
  return candidate.benchmark;
}

function statusBadge(recording: RecordingManifest) {
  if (recording.status === 'complete') return 'badge green';
  if (recording.status === 'failed') return 'badge red';
  return 'badge warning';
}

function socketBadgeClass(status: string) {
  if (status === 'connected') return 'badge green';
  if (status === 'connecting' || status === 'reconnecting') return 'badge warning';
  return 'badge red';
}

function formatActionError(error: unknown) {
  return error instanceof Error ? error.message : 'The action failed. Please try again.';
}

function formatBackendLoadError(error: unknown) {
  const detail = error instanceof Error ? error.message : 'API request failed.';
  return `Backend unavailable: API did not finish startup. Check /health and docker compose logs api postgres. ${detail}`;
}

function parseTickerInput(value: string) {
  return value
    .split(/[\s,]+/)
    .map((item) => item.trim().toUpperCase())
    .filter(Boolean)
    .filter((item, index, all) => all.indexOf(item) === index)
    .slice(0, 10);
}

function defaultReplayDate() {
  const date = new Date();
  date.setDate(date.getDate() - 1);
  while (date.getDay() === 0 || date.getDay() === 6) {
    date.setDate(date.getDate() - 1);
  }
  return date.toISOString().slice(0, 10);
}

function TerminalLoadingOverlay({
  label,
  progress
}: {
  label: string;
  progress?: number | null;
}) {
  return (
    <div className="terminal-loader-backdrop" role="status" aria-live="polite">
      <div className="terminal-loader">
        <div className="terminal-spinner" aria-hidden="true" />
        <strong>{label}</strong>
        {progress !== undefined && (
          <div className="terminal-loader-progress">
            <progress
              aria-label="Replay loading progress"
              max={1}
              value={progress === null ? undefined : progress}
            />
            <span className="muted">
              {progress === null ? 'Preparing replay timeline' : `${Math.round(progress * 100)}%`}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

export function DashboardPage() {
  const queryClient = useQueryClient();
  const scenarios = useQuery({ queryKey: ['scenarios'], queryFn: listScenarios });
  const recordings = useQuery({ queryKey: ['recordings'], queryFn: listRecordings, refetchInterval: 5000 });
  const [mode, setMode] = useState<DashboardMode>('launcher');
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [pendingProgress, setPendingProgress] = useState<number | null | undefined>(undefined);
  const [actionError, setActionError] = useState<string | null>(null);
  const [scenarioId, setScenarioId] = useState('2024-05-10');
  const [durationMinutes, setDurationMinutes] = useState(60);
  const [recordingName, setRecordingName] = useState('');
  const [marketDataMode, setMarketDataMode] = useState<MarketDataMode>('synthetic');
  const [realMarketTickers, setRealMarketTickers] = useState(
    'AAPL,NVDA,MSFT,TSLA,AMD,AMZN,META,GOOGL,JPM,XOM'
  );
  const [replayDate, setReplayDate] = useState(defaultReplayDate);
  const [selectedSymbol, setSelectedSymbol] = useState('ALPH');
  const [simulationId, setSimulationId] = useState<string | null>(null);
  const [activeRecording, setActiveRecording] = useState<RecordingManifest | null>(null);
  const [localSnapshot, setLocalSnapshot] = useState<SimulationSnapshot | null>(null);
  const [replayFrames, setReplayFrames] = useState<SimulationRecordingFrame[]>([]);
  const [replayKeyframes, setReplayKeyframes] = useState<ReplayKeyframe[]>([]);
  const [replayBenchmarkRun, setReplayBenchmarkRun] = useState<ReplayBenchmarkRun | null>(null);
  const [rawReplayFramesLoaded, setRawReplayFramesLoaded] = useState(false);
  const [replayIndex, setReplayIndex] = useState(0);
  const [replayPlaying, setReplayPlaying] = useState(false);
  const [replaySpeed, setReplaySpeed] = useState(5);
  const [replayTimelineMode, setReplayTimelineMode] = useState<ReplayTimelineMode>('actions');
  const socket = useSimulationSocket(mode === 'live' ? simulationId : null);
  const actualMarketMode =
    scenarioId === 'actual-market' || marketDataMode === 'yfinance' || marketDataMode === 'alpaca';
  const requestedTickers = parseTickerInput(realMarketTickers);
  const marketDataRequest = actualMarketMode
    ? {
        market_data_mode: marketDataMode === 'alpaca' ? ('alpaca' as const) : ('yfinance' as const),
        real_market_tickers: requestedTickers,
        replay_date: replayDate
      }
    : { market_data_mode: 'synthetic' as const };
  const estimate = useQuery({
    queryKey: ['simulation-estimate', scenarioId, durationMinutes, marketDataMode, realMarketTickers, replayDate],
    queryFn: () => estimateSimulation(scenarioId, durationMinutes, marketDataRequest),
    enabled: mode === 'launcher'
  });
  const activeReplayLength = timelineLength(replayFrames, replayKeyframes, replayTimelineMode);
  const replayFrame = frameAtTimelineIndex(replayFrames, replayKeyframes, replayTimelineMode, replayIndex);
  const replaySnapshot = replayFrame?.snapshot ?? null;
  const replayBenchmark = benchmarkForReplayFrame(replayBenchmarkRun, replayFrame?.index ?? null);
  const replaySnapshotWithBenchmark = useMemo(() => {
    if (!replaySnapshot || !replayBenchmark) return replaySnapshot;
    if (replaySnapshot.benchmark?.benchmark_run_id === replayBenchmark.benchmark_run_id) {
      return replaySnapshot;
    }
    return { ...replaySnapshot, benchmark: replayBenchmark };
  }, [replayBenchmark, replaySnapshot]);
  const activeKeyframe = replayTimelineMode === 'actions' ? replayKeyframes[replayIndex] : null;
  const snapshot = mode === 'replay' ? replaySnapshotWithBenchmark : socket.snapshot ?? localSnapshot;
  const scenarioOptions = scenarios.data?.scenarios ?? [];
  const recordingOptions = recordings.data?.recordings ?? [];
  const scenariosError = scenarios.isError ? formatBackendLoadError(scenarios.error) : null;
  const recordingsError = recordings.isError ? formatBackendLoadError(recordings.error) : null;
  const symbolMeta = useMemo(() => {
    const instruments = snapshot?.instruments ?? [];
    if (instruments.length > 0) {
      return instruments.map((instrument) => ({
        symbol: instrument.symbol,
        name: instrument.display_name || instrument.symbol
      }));
    }
    const symbols = Array.from(
      new Set([
        ...(snapshot?.orderbooks.map((book) => book.symbol) ?? []),
        ...(snapshot?.history_bars.map((bar) => bar.symbol) ?? [])
      ])
    );
    return symbols.map((symbol) => ({ symbol, name: symbol }));
  }, [snapshot]);
  const selectedScenario = scenarioOptions.find((scenario) => scenario.id === scenarioId);
  const recordingDetailLoader = useMemo(() => {
    if (mode !== 'replay' || !activeRecording) return undefined;
    return {
      load: (activityId: string) => getRecordingActivityDetail(activeRecording.recording_id, activityId)
    };
  }, [activeRecording, mode]);
  const workspacePanels: WorkspacePanel[] = snapshot
    ? [
        {
          id: 'market-candles',
          title: 'Market Replay Candles',
          category: 'Market',
          defaultVisible: true,
          defaultSpan: 8,
          defaultRows: 1,
          minRows: 1,
          compactClass: 'compact-candles',
          render: () => (
            <section className="panel">
              <h2>Market Replay Candles</h2>
              <div className="panel-body">
                <div className="symbol-filter">
                  {symbolMeta.map(({ symbol, name }) => (
                    <button
                      className={selectedSymbol === symbol ? 'active' : ''}
                      key={symbol}
                      onClick={() => setSelectedSymbol(symbol)}
                    >
                      <strong>{symbol}</strong>
                      <span>{name}</span>
                    </button>
                  ))}
                </div>
                {snapshot.market_data.warning && (
                  <p className="muted market-warning">{snapshot.market_data.warning}</p>
                )}
                <CandlestickChart
                  bars={snapshot.history_bars.filter((bar) => bar.symbol === selectedSymbol)}
                  symbol={selectedSymbol}
                />
              </div>
            </section>
          )
        },
        {
          id: 'agent-society-live',
          title: 'Agent Society Live',
          category: 'Agents',
          defaultVisible: true,
          defaultSpan: 4,
          defaultRows: 1,
          minRows: 1,
          compactClass: 'compact-agent-live',
          render: () => (
            <AgentSocietyLive
              snapshot={snapshot}
              emptyReason={agentEmptyReason(snapshot)}
              activityDetailLoader={recordingDetailLoader}
            />
          )
        },
        {
          id: 'orderbook',
          title: 'Order Book',
          category: 'Market',
          defaultVisible: true,
          defaultSpan: 8,
          defaultRows: 1,
          minRows: 1,
          compactClass: 'compact-orderbook',
          render: () => <OrderBookPanel orderbooks={snapshot.orderbooks} trades={snapshot.trade_tape} />
        },
        {
          id: 'portfolio',
          title: 'Portfolio',
          category: 'Market',
          defaultVisible: true,
          defaultSpan: 4,
          defaultRows: 1,
          minRows: 1,
          compactClass: 'compact-portfolio',
          render: () => (
            <PortfolioPanel
              portfolio={snapshot.portfolio}
              history={snapshot.portfolio_history}
              decisions={snapshot.agent_decisions}
              trades={snapshot.trade_tape}
            />
          )
        },
        {
          id: 'released-events',
          title: 'Released Events',
          category: 'Market',
          defaultVisible: false,
          defaultSpan: 6,
          render: () => (
            <section className="panel span-12">
              <h2>Released Events</h2>
              <div className="panel-body timeline compact-scroll-card">
                {snapshot.released_events.length === 0 ? (
                  <p className="muted">No released events yet.</p>
                ) : (
                  snapshot.released_events.map((event) => (
                    <article
                      className={`event ${event.sentiment_hint === 'bearish' ? 'negative' : event.sentiment_hint}`}
                      key={event.id}
                    >
                      <div className="list-row">
                        <strong>{event.headline}</strong>
                        <span className="badge">S{event.severity}</span>
                      </div>
                      <p className="muted">{event.body}</p>
                    </article>
                  ))
                )}
              </div>
            </section>
          )
        },
        {
          id: 'agent-runtime',
          title: 'Agent Runtime',
          category: 'Diagnostics',
          defaultVisible: false,
          defaultSpan: 12,
          render: () => (
            <section className="panel span-12">
              <h2>Agent Runtime</h2>
              <div className="panel-body agent-runtime">
                <div className="runtime-grid">
                  <div className="stat-row">
                    <span>Status</span>
                    <strong>{snapshot.agent_cycle_status ?? 'idle'}</strong>
                  </div>
                  <div className="stat-row">
                    <span>Active agent</span>
                    <span className="mono">{snapshot.active_agent ?? 'none'}</span>
                  </div>
                  <div className="stat-row">
                    <span>AI runtime</span>
                    <strong>{snapshot.agent_cycle_status === 'running' ? 'active' : 'ready'}</strong>
                  </div>
                  <div className="stat-row">
                    <span>LLM calls</span>
                    <strong>{snapshot.last_llm_calls ?? 0}</strong>
                  </div>
                  <div className="stat-row">
                    <span>Tokens</span>
                    <strong>{(snapshot.last_llm_tokens ?? 0).toLocaleString()}</strong>
                  </div>
                </div>
                <div className="runtime-progress">
                  <div className="list-row tight">
                    <span className="muted">Cycle progress</span>
                    <span className="mono">
                      {snapshot.completed_llm_calls ?? 0}/{snapshot.expected_llm_calls ?? 0}
                    </span>
                  </div>
                  <progress
                    aria-label="Agent LLM call progress"
                    className="progress"
                    max={1}
                    value={agentProgressRatio(snapshot)}
                  />
                  {snapshot.last_llm_error ? (
                    <p className="muted">Fallback used after AI runtime error: {snapshot.last_llm_error}</p>
                  ) : snapshot.last_fallback_reason ? (
                    <p className="muted">
                      Last fallback: {snapshot.last_fallback_agent ?? 'agent'} - {snapshot.last_fallback_reason}
                    </p>
                  ) : (
                    <p className="muted">{agentEmptyReason(snapshot)}</p>
                  )}
                </div>
              </div>
            </section>
          )
        },
        {
          id: 'candidate-slate',
          title: 'Candidate Slate',
          category: 'Agents',
          defaultVisible: false,
          defaultSpan: 12,
          render: () => (
            <CandidateSlatePanel
              candidates={snapshot.candidate_slate}
              decisions={snapshot.agent_decisions}
            />
          )
        },
        {
          id: 'agent-workbench',
          title: 'Agent Workbench',
          category: 'Agents',
          defaultVisible: false,
          defaultSpan: 6,
          render: () => (
            <AgentWorkbench
              agents={snapshot.agent_states}
              debate={snapshot.debate}
              decisions={snapshot.agent_decisions}
              emptyReason={agentEmptyReason(snapshot)}
            />
          )
        },
        {
          id: 'investment-committee',
          title: 'Investment Committee',
          category: 'Governance',
          defaultVisible: false,
          defaultSpan: 6,
          render: () => (
            <InvestmentCommitteeBoard
              className="span-12"
              decisions={snapshot.committee_decisions}
              consensus={snapshot.consensus}
              conflicts={snapshot.conflicts}
              agents={snapshot.agent_states}
              debate={snapshot.debate}
            />
          )
        },
        {
          id: 'benchmark',
          title: 'Agent Society Benchmark',
          category: 'Governance',
          defaultVisible: false,
          defaultSpan: 6,
          render: () => (
            <BenchmarkCard
              className="span-12"
              benchmark={snapshot.benchmark}
              onRun={benchmark}
              replayBenchmark={mode === 'replay' ? replayBenchmarkRun : null}
            />
          )
        },
        {
          id: 'decision-flow',
          title: 'Agent Decision Flow',
          category: 'Diagnostics',
          defaultVisible: false,
          defaultSpan: 12,
          render: () => (
            <AgentDecisionFlow
              decisions={snapshot.agent_decisions}
              positions={snapshot.portfolio.positions}
              emptyReason={agentEmptyReason(snapshot)}
            />
          )
        }
      ]
    : [];

  useEffect(() => {
    if (mode !== 'replay' || !replayPlaying) return;
    const timer = window.setInterval(
      () =>
        setReplayIndex((current) => {
          if (current >= activeReplayLength - 1) {
            setReplayPlaying(false);
            return current;
          }
          return current + 1;
        }),
      replayDelayForSpeed(replaySpeed)
    );
    return () => window.clearInterval(timer);
  }, [activeReplayLength, mode, replayPlaying, replaySpeed]);

  useEffect(() => {
    if (mode !== 'replay') return;
    if (replayIndex > Math.max(0, activeReplayLength - 1)) {
      setReplayIndex(0);
      setReplayPlaying(false);
    }
  }, [activeReplayLength, mode, replayIndex]);

  useEffect(() => {
    setReplayIndex(0);
    setReplayPlaying(false);
  }, [replayTimelineMode]);

  useEffect(() => {
    if (symbolMeta.length === 0) return;
    if (!symbolMeta.some((item) => item.symbol === selectedSymbol)) {
      setSelectedSymbol(symbolMeta[0].symbol);
    }
  }, [selectedSymbol, symbolMeta]);

  async function refreshRecordings() {
    await queryClient.invalidateQueries({ queryKey: ['recordings'] });
  }

  async function withPending<T>(
    label: string,
    task: () => Promise<T>,
    progress?: number | null
  ) {
    if (pendingAction) return undefined;
    setActionError(null);
    setPendingAction(label);
    setPendingProgress(progress);
    try {
      return await task();
    } catch (error) {
      setActionError(formatActionError(error));
      return undefined;
    } finally {
      setPendingAction(null);
      setPendingProgress(undefined);
    }
  }

  async function startRecordedSimulation() {
    await withPending('Creating recorded simulation', async () => {
      const created = await createRecordedSimulation(
        scenarioId,
        durationMinutes,
        recordingName.trim() || selectedScenario?.title,
        marketDataRequest
      );
      setActiveRecording(created.recording);
      setSimulationId(created.snapshot.simulation_id);
      setLocalSnapshot(created.snapshot);
      setReplayFrames([]);
      setReplayKeyframes([]);
      setReplayBenchmarkRun(null);
      setRawReplayFramesLoaded(false);
      setReplayIndex(0);
      setMode('live');
      await refreshRecordings();
    });
  }

  async function send(action: 'start' | 'pause' | 'resume' | 'step' | 'reset') {
    if (!simulationId) return;
    const updated = await controlSimulation(simulationId, action);
    setLocalSnapshot(updated);
    if (action === 'reset') setSimulationId(updated.simulation_id);
  }

  async function changeSpeed(speed: number) {
    if (!simulationId) return;
    setLocalSnapshot(await setSpeed(simulationId, speed));
  }

  async function stopAndSave() {
    if (!simulationId) return;
    await withPending('Stopping and saving replay', async () => {
      const stopped = await stopAndSaveSimulation(simulationId);
      setLocalSnapshot(stopped.snapshot);
      await refreshRecordings();
      if (stopped.recording) {
        await loadReplay(stopped.recording.recording_id, stopped.recording, false);
      }
    });
  }

  async function benchmark() {
    if (mode === 'replay' && activeRecording) {
      await withPending(
        'Benchmarking replay keyframes',
        async () => {
          setReplayBenchmarkRun(null);
          setReplayBenchmarkRun(await runRecordingBenchmark(activeRecording.recording_id));
        },
        null
      );
      return;
    }
    await withPending('Running benchmark', async () => {
      if (simulationId) {
        const updated = await runSimulationBenchmark(simulationId);
        setLocalSnapshot(updated.snapshot);
      }
    });
  }

  async function loadRawReplayFrames(recordingId: string, frameCount?: number) {
    const pageSize = 1000;
    const frames: SimulationRecordingFrame[] = [];
    let offset = 0;
    const expectedFrames = Math.max(1, frameCount ?? pageSize);
    setPendingProgress(0);
    while (frameCount === undefined || offset < frameCount) {
      const limit = frameCount === undefined ? pageSize : Math.min(pageSize, frameCount - offset);
      const loaded = await getRecordingFrames(recordingId, offset, limit);
      frames.push(...loaded.frames);
      setPendingProgress(Math.min(1, frames.length / expectedFrames));
      if (loaded.frames.length < limit) break;
      offset += loaded.frames.length;
    }
    setReplayFrames(frames);
    setRawReplayFramesLoaded(true);
    return frames;
  }

  async function switchReplayTimelineMode(nextMode: ReplayTimelineMode) {
    if (nextMode === 'frames' && !rawReplayFramesLoaded) {
      if (!activeRecording) return;
      await withPending('Loading raw replay frames', async () => {
        await loadRawReplayFrames(activeRecording.recording_id, activeRecording.frame_count);
        setReplayTimelineMode('frames');
      }, 0);
      return;
    }
    setReplayTimelineMode(nextMode);
  }

  async function loadReplay(recordingId: string, manifest?: RecordingManifest, showPending = true) {
    const load = async () => {
      const loaded = await getRecordingKeyframes(recordingId);
      const keyframes = loaded.keyframes.map((keyframe) => ({
        frame: keyframe.frame,
        frameIndex: keyframe.frame_index,
        eventIndex: keyframe.event_index,
        reason: keyframe.reason
      }));
      setReplayKeyframes(keyframes);
      setReplayFrames([]);
      setReplayBenchmarkRun(null);
      setRawReplayFramesLoaded(false);
      setReplayIndex(0);
      setReplayPlaying(false);
      setReplayTimelineMode('actions');
      setActiveRecording(manifest ?? recordings.data?.recordings.find((item) => item.recording_id === recordingId) ?? null);
      setSimulationId(null);
      setLocalSnapshot(keyframes[0]?.frame.snapshot ?? null);
      setMode('replay');
    };
    if (showPending) await withPending('Loading action replay', load, null);
    else await load();
  }

  async function continueRecording(recordingId: string) {
    await withPending('Continuing live simulation', async () => {
      const resumed = await resumeRecording(recordingId);
      setActiveRecording(resumed.recording);
      setSimulationId(resumed.snapshot.simulation_id);
      setLocalSnapshot(resumed.snapshot);
      setReplayFrames([]);
      setReplayKeyframes([]);
      setReplayBenchmarkRun(null);
      setRawReplayFramesLoaded(false);
      setReplayIndex(0);
      setReplayPlaying(false);
      setMode('live');
      await refreshRecordings();
    });
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand">
          <h1>Agentic Hedge Fund</h1>
          <span>Replay-first agent society demo. No investment advice. No real trades.</span>
        </div>
        <div className="toolbar">
          {mode === 'live' && (
            <span className={socketBadgeClass(socket.status)}>
              <Activity size={14} />
              {socket.status}
            </span>
          )}
          {mode === 'replay' && (
            <span className="badge green">
              <Archive size={14} />
              replay
            </span>
          )}
          <button className="btn" onClick={() => setMode('launcher')}>
            <Archive size={16} />
            Simulations
          </button>
        </div>
      </header>

      {actionError && (
        <div className="app-error" role="alert">
          <strong>Action failed</strong>
          <span>{actionError}</span>
          <button className="icon-btn" type="button" onClick={() => setActionError(null)}>
            x
          </button>
        </div>
      )}

      {mode === 'launcher' && (
        <section className="launcher-grid">
          <section className="panel">
            <h2>New Recorded Simulation</h2>
            <div className="panel-body launcher-panel">
              <label>
                <span className="muted">Scenario</span>
                {scenariosError && (
                  <div className="inline-error" role="alert">
                    <strong>Backend unavailable</strong>
                    <span>{scenariosError}</span>
                  </div>
                )}
                  <select
                    className="select"
                    value={scenarioId}
                    disabled={scenarios.isLoading || Boolean(scenariosError)}
                    onChange={(event) => {
                      const nextScenario = event.target.value;
                      setScenarioId(nextScenario);
                      setMarketDataMode(nextScenario === 'actual-market' ? 'yfinance' : 'synthetic');
                    }}
                  >
                  {scenarios.isLoading && <option value={scenarioId}>Loading scenarios...</option>}
                  {scenariosError && <option value={scenarioId}>Scenarios unavailable</option>}
                  {!scenarios.isLoading &&
                    !scenariosError &&
                    scenarioOptions.map((scenario) => (
                      <option value={scenario.id} key={scenario.id}>
                        {scenario.display_date} - {scenario.title}
                      </option>
                    ))}
                </select>
              </label>
              <div>
                <span className="muted">Market data</span>
                <div className="toolbar">
                  <button
                    className={!actualMarketMode ? 'btn active' : 'btn'}
                    onClick={() => {
                      setMarketDataMode('synthetic');
                      if (scenarioId === 'actual-market') setScenarioId('2024-05-10');
                    }}
                  >
                    Synthetic
                  </button>
                  <button
                    className={actualMarketMode ? 'btn active' : 'btn'}
                    onClick={() => {
                      setMarketDataMode('yfinance');
                      setScenarioId('actual-market');
                    }}
                  >
                    Historical market
                  </button>
                </div>
              </div>
              {actualMarketMode && (
                <div className="market-data-fields">
                  <div>
                    <span className="muted">Historical feed</span>
                    <div className="toolbar">
                      <button
                        className={marketDataMode !== 'alpaca' ? 'btn active' : 'btn'}
                        onClick={() => setMarketDataMode('yfinance')}
                      >
                        yfinance
                      </button>
                      <button
                        className={marketDataMode === 'alpaca' ? 'btn active' : 'btn'}
                        onClick={() => setMarketDataMode('alpaca')}
                      >
                        Alpaca
                      </button>
                    </div>
                  </div>
                  <label>
                    <span className="muted">Tickers</span>
                    <input
                      className="input mono"
                      value={realMarketTickers}
                      onChange={(event) => setRealMarketTickers(event.target.value)}
                      placeholder="AAPL,NVDA,MSFT,TSLA,AMD,AMZN,META,GOOGL,JPM,XOM"
                    />
                  </label>
                  <label>
                    <span className="muted">Replay date</span>
                    <input
                      className="input"
                      type="date"
                      value={replayDate}
                      onChange={(event) => setReplayDate(event.target.value)}
                    />
                  </label>
                  <p className="muted">
                    Uses yfinance historical bars for up to 10 tickers by default. 1-minute intraday
                    data is limited to recent history; older dates may use daily-shaped replay or
                    generated fallback.
                  </p>
                </div>
              )}
              <label>
                <span className="muted">Recording name</span>
                <input
                  className="input"
                  value={recordingName}
                  onChange={(event) => setRecordingName(event.target.value)}
                  placeholder={selectedScenario?.title ?? 'Demo recording'}
                />
              </label>
              <div>
                <span className="muted">Simulated duration</span>
                <div className="toolbar">
                  {durationOptions.map((duration) => (
                    <button
                      className={durationMinutes === duration ? 'btn active' : 'btn'}
                      key={duration}
                      onClick={() => setDurationMinutes(duration)}
                    >
                      {duration === 390 ? 'Full day' : `${duration}m`}
                    </button>
                  ))}
                </div>
              </div>
              <div className="estimate-box">
                <strong>{estimate.data ? `Estimated live time: ${formatTime(estimate.data.estimated_real_seconds)}` : 'Estimating live time...'}</strong>
                <p className="muted">
                  {estimate.data?.warning ??
                    'Live recording waits for real LLM calls. Saved replays can be scrubbed and sped up instantly.'}
                </p>
              </div>
              <button
                className="btn primary"
                disabled={Boolean(pendingAction) || Boolean(scenariosError) || scenarioOptions.length === 0}
                onClick={startRecordedSimulation}
              >
                <Play size={16} />
                Create recording
              </button>
            </div>
          </section>

          <section className="panel">
            <h2>Saved Simulations</h2>
            <div className="panel-body recording-list">
              {recordingsError ? (
                <div className="inline-error" role="alert">
                  <strong>Backend unavailable</strong>
                  <span>{recordingsError}</span>
                </div>
              ) : recordings.isLoading ? (
                <p className="muted">Loading saved simulations...</p>
              ) : recordingOptions.length === 0 ? (
                <p className="muted">No saved simulations yet. Create a recording to unlock instant replay.</p>
              ) : (
                recordingOptions.map((recording) => (
                  <article className="recording-card" key={recording.recording_id}>
                    <div>
                      <div className="list-row tight">
                        <strong>{recording.name}</strong>
                        <span className={statusBadge(recording)}>{recording.status}</span>
                      </div>
                      <p className="muted">
                  {recording.scenario_title} | {recording.duration_minutes}m target | {recording.frame_count}{' '}
                        frames | {recording.market_data_mode ?? 'synthetic'}
                        {recording.tickers?.length ? ` | ${recording.tickers.join(', ')}` : ''}
                      </p>
                    </div>
                    <div className="toolbar">
                      <button
                        className="btn primary"
                        disabled={Boolean(pendingAction)}
                        onClick={() => loadReplay(recording.recording_id, recording)}
                      >
                        <Play size={15} />
                        Replay
                      </button>
                      {recording.can_continue && (
                        <button
                          className="btn"
                          disabled={Boolean(pendingAction)}
                          onClick={() => continueRecording(recording.recording_id)}
                        >
                          <SkipForward size={15} />
                          Continue
                        </button>
                      )}
                    </div>
                  </article>
                ))
              )}
            </div>
          </section>
        </section>
      )}

      {mode === 'live' && snapshot && (
        <section className="topbar static">
          <div className="toolbar">
            <button className="btn primary" onClick={() => send('start')} title="Start">
              <Play size={16} />
              Start
            </button>
            <button className="btn" onClick={() => send('pause')} title="Pause">
              <Pause size={16} />
              Pause
            </button>
            <button className="btn" onClick={() => send('resume')} title="Resume">
              <SkipForward size={16} />
              Resume
            </button>
            <button className="btn" onClick={() => send('step')} title="Step one tick">
              <StepForward size={16} />
              Step
            </button>
            <button className="btn" onClick={() => send('reset')} title="Reset">
              <RotateCcw size={16} />
              Reset
            </button>
            {liveSpeeds.map((speed) => (
              <button className="btn" key={speed} onClick={() => changeSpeed(speed)}>
                {speed}x
              </button>
            ))}
            <button className="btn warning" disabled={Boolean(pendingAction)} onClick={stopAndSave}>
              <Save size={15} />
              Stop and save
            </button>
          </div>
          <div className="toolbar">
            <span className="badge">{snapshot.status}</span>
            <span className="badge mono">{new Date(snapshot.current_time).toLocaleTimeString()}</span>
            <span className="badge">speed {snapshot.speed}x</span>
            <span className="badge">market {snapshot.market_data.feed}</span>
            <span className={snapshot.agent_cycle_status === 'running' ? 'badge green' : 'badge'}>
              <BrainCircuit size={14} />
              {snapshot.agent_cycle_status ?? 'idle'}
            </span>
          </div>
        </section>
      )}

      {mode === 'replay' && snapshot && (
        <section className="topbar static">
          <div className="toolbar replay-controls">
            <button className="btn primary" onClick={() => setReplayPlaying((playing) => !playing)}>
              {replayPlaying ? <Pause size={16} /> : <Play size={16} />}
              {replayPlaying ? 'Pause replay' : 'Play replay'}
            </button>
            {replaySpeeds.map((speed) => (
              <button
                className={replaySpeed === speed ? 'btn active' : 'btn'}
                key={speed}
                onClick={() => setReplaySpeed(speed)}
              >
                {speed}x
              </button>
            ))}
            <button
              className={replayTimelineMode === 'actions' ? 'btn active' : 'btn'}
              onClick={() => void switchReplayTimelineMode('actions')}
            >
              Action replay
            </button>
            <button
              className={replayTimelineMode === 'frames' ? 'btn active' : 'btn'}
              onClick={() => void switchReplayTimelineMode('frames')}
            >
              Full frames
            </button>
            <input
              aria-label={replayTimelineMode === 'actions' ? 'Replay event' : 'Replay frame'}
              className="replay-slider"
              max={Math.max(0, activeReplayLength - 1)}
              min={0}
              onChange={(event) => setReplayIndex(Number(event.target.value))}
              type="range"
              value={replayIndex}
            />
            <span className="badge mono">
              {replayTimelineMode === 'actions' ? 'event' : 'frame'} {replayIndex + 1}/
              {Math.max(1, activeReplayLength)}
            </span>
            <span className="badge mono">
              source frame {replayFrame?.index ?? activeKeyframe?.frameIndex ?? 0}
            </span>
            {activeKeyframe && <span className="badge green">{activeKeyframe.reason}</span>}
            <span className="badge">
              {replayTimelineMode === 'actions' ? 'equal action spacing' : 'raw recorded frames'}
            </span>
            {activeRecording?.can_continue && (
              <button
                className="btn"
                disabled={Boolean(pendingAction)}
                onClick={() => continueRecording(activeRecording.recording_id)}
              >
                <SkipForward size={15} />
                Continue live
              </button>
            )}
          </div>
          <div className="toolbar">
            <span className="badge green">saved replay</span>
            <span className="badge mono">{new Date(snapshot.current_time).toLocaleTimeString()}</span>
            <span className="badge">{activeRecording?.name ?? 'recording'}</span>
            <span className="badge">market {snapshot.market_data.feed}</span>
          </div>
        </section>
      )}

      {mode !== 'launcher' && snapshot ? (
        <DockableWorkspace panels={workspacePanels} storageKey="agentic-workspace-layout-v3" />
      ) : mode !== 'launcher' ? (
        <div className="panel m-4">
          <div className="panel-body">Loading simulation...</div>
        </div>
      ) : null}
      {pendingAction && <TerminalLoadingOverlay label={pendingAction} progress={pendingProgress} />}
      <HumanApprovalModal open={false} />
    </main>
  );
}
