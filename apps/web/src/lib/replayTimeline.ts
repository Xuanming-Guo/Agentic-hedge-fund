import type { SimulationRecordingFrame, SimulationSnapshot } from './types';

export type ReplayTimelineMode = 'actions' | 'frames';

export type ReplayKeyframe = {
  frame: SimulationRecordingFrame;
  frameIndex: number;
  eventIndex: number;
  reason: string;
};

const replayDelayBySpeed: Record<number, number> = {
  1: 1200,
  5: 450,
  20: 120
};

type SnapshotSignature = {
  releasedEvents: number;
  agentActivity: number;
  agentStatus: string;
  activeAgent: string;
  agentStates: string;
  debate: number;
  decisions: number;
  committees: number;
  consensus: number;
  trades: number;
  positions: string;
  pnl: string;
  benchmark: string;
};

export function replayDelayForSpeed(speed: number) {
  return replayDelayBySpeed[speed] ?? Math.max(80, Math.round(1200 / Math.max(1, speed)));
}

export function frameAtTimelineIndex(
  frames: SimulationRecordingFrame[],
  keyframes: ReplayKeyframe[],
  mode: ReplayTimelineMode,
  index: number
) {
  if (mode === 'frames') return frames[index] ?? frames[0] ?? null;
  return keyframes[index]?.frame ?? keyframes[0]?.frame ?? frames[0] ?? null;
}

export function timelineLength(
  frames: SimulationRecordingFrame[],
  keyframes: ReplayKeyframe[],
  mode: ReplayTimelineMode
) {
  return mode === 'frames' ? frames.length : keyframes.length;
}

export function deriveReplayKeyframes(frames: SimulationRecordingFrame[]) {
  const keyframes: ReplayKeyframe[] = [];
  let previous: SnapshotSignature | null = null;

  frames.forEach((frame, frameIndex) => {
    const current = signatureFor(frame.snapshot);
    const reason = previous ? changeReason(previous, current) : initialReason(current);
    if (reason) {
      keyframes.push({
        frame,
        frameIndex,
        eventIndex: keyframes.length,
        reason
      });
    }
    previous = current;
  });

  if (keyframes.length > 0) return keyframes;
  return frames.length > 0
    ? [{ frame: frames[0], frameIndex: 0, eventIndex: 0, reason: 'Initial frame' }]
    : [];
}

function initialReason(signature: SnapshotSignature) {
  if (signature.releasedEvents > 0) return 'Released event';
  if (signature.agentActivity > 0) return 'Agent activity';
  if (signature.decisions > 0 || signature.committees > 0) return 'Investment decision';
  if (signature.trades > 0) return 'Trade tape';
  if (signature.positions !== 'flat') return 'Portfolio position';
  if (signature.benchmark !== 'none') return 'Benchmark';
  if (signature.agentStatus === 'running') return 'Agent cycle running';
  return null;
}

function changeReason(previous: SnapshotSignature, current: SnapshotSignature) {
  if (current.releasedEvents > previous.releasedEvents) return 'Released event';
  if (current.agentActivity > previous.agentActivity) return 'Agent activity';
  if (current.agentStatus !== previous.agentStatus || current.activeAgent !== previous.activeAgent) {
    return 'Agent runtime transition';
  }
  if (current.agentStates !== previous.agentStates) return 'Agent state update';
  if (current.debate > previous.debate) return 'Agent debate';
  if (current.decisions > previous.decisions) return 'Agent decision';
  if (current.committees > previous.committees) return 'Committee decision';
  if (current.consensus > previous.consensus) return 'Consensus update';
  if (current.trades > previous.trades) return 'Execution fill';
  if (current.positions !== previous.positions || current.pnl !== previous.pnl) {
    return 'Portfolio update';
  }
  if (current.benchmark !== previous.benchmark) return 'Benchmark update';
  return null;
}

function signatureFor(snapshot: SimulationSnapshot): SnapshotSignature {
  return {
    releasedEvents: snapshot.released_events.length,
    agentActivity: snapshot.agent_activity_feed?.length ?? 0,
    agentStatus: snapshot.agent_cycle_status ?? 'idle',
    activeAgent: snapshot.active_agent ?? '',
    agentStates: snapshot.agent_states
      .map((agent) =>
        [
          agent.agent_id,
          agent.status,
          agent.last_action,
          agent.target_symbol ?? '',
          agent.decision ?? '',
          agent.quantity ?? ''
        ].join(':')
      )
      .join('|'),
    debate: snapshot.debate.length,
    decisions: snapshot.agent_decisions.length,
    committees: snapshot.committee_decisions.length,
    consensus: snapshot.consensus.length,
    trades: snapshot.trade_tape.length,
    positions:
      snapshot.portfolio.positions.length === 0
        ? 'flat'
        : snapshot.portfolio.positions
            .map((position) => `${position.symbol}:${position.quantity}:${position.market_value.toFixed(0)}`)
            .sort()
            .join('|'),
    pnl: [
      snapshot.portfolio.realized_pnl.toFixed(0),
      snapshot.portfolio.unrealized_pnl.toFixed(0),
      snapshot.portfolio.gross_exposure.toFixed(0)
    ].join(':'),
    benchmark: snapshot.benchmark
      ? `${snapshot.benchmark.benchmark_run_id}:${snapshot.benchmark.score.toFixed(3)}`
      : 'none'
  };
}

