import { describe, expect, test } from 'vitest';
import {
  deriveReplayKeyframes,
  frameAtTimelineIndex,
  replayDelayForSpeed,
  timelineLength
} from './replayTimeline';
import type { SimulationRecordingFrame, SimulationSnapshot } from './types';

function snapshot(overrides: Partial<SimulationSnapshot> = {}): SimulationSnapshot {
  return {
    simulation_id: 'sim-test',
    scenario: {
      id: '2024-05-10',
      display_date: '2024-05-10',
      title: 'Test',
      description: 'Test',
      seed: 1,
      status: 'active'
    },
    instruments: [],
    market_data: {
      mode: 'synthetic',
      provider: 'synthetic',
      feed: 'synthetic',
      is_delayed: false,
      quote_source: 'synthetic',
      depth_source: 'synthetic_limit_order_book',
      requested_tickers: [],
      active_tickers: [],
      replay_date: '2024-05-10',
      warning: null
    },
    status: 'running',
    current_time: '2024-05-10T09:30:00-04:00',
    speed: 1,
    released_events: [],
    latest_bars: [],
    history_bars: [],
    orderbooks: [],
    trade_tape: [],
    portfolio: {
      cash: 1000000,
      equity: 1000000,
      realized_pnl: 0,
      unrealized_pnl: 0,
      gross_exposure: 0,
      net_exposure: 0,
      sector_exposure: {},
      positions: []
    },
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
    ...overrides
  };
}

function frame(index: number, overrides: Partial<SimulationSnapshot> = {}): SimulationRecordingFrame {
  return {
    index,
    timestamp: `2024-05-10T09:${String(30 + index).padStart(2, '0')}:00-04:00`,
    elapsed_sim_minutes: index,
    snapshot: snapshot(overrides)
  };
}

describe('replay timeline', () => {
  test('skips quiet startup frames and starts at the first meaningful action', () => {
    const frames = [
      frame(0),
      frame(1),
      frame(2, {
        released_events: [
          {
            id: 'evt-1',
            timestamp: '2024-05-10T09:32:00-04:00',
            headline: 'Macro shock',
            body: 'Rates move.',
            affected_symbols: ['ECHO'],
            severity: 4,
            sentiment_hint: 'bearish',
            event_type: 'macro'
          }
        ]
      }),
      frame(3, {
        agent_activity_feed: [
          {
            id: 'act-1',
            timestamp: '2024-05-10T09:33:00-04:00',
            cycle_id: 'cycle-1',
            kind: 'agent_completed',
            agent_id: 'MacroAnalystAgent',
            title: 'Macro complete',
            message: 'Rates pressure ECHO.',
            evidence_ids: ['evt-1'],
            tool_call_ids: []
          }
        ]
      })
    ];

    const keyframes = deriveReplayKeyframes(frames);

    expect(keyframes).toHaveLength(2);
    expect(keyframes[0].frameIndex).toBe(2);
    expect(keyframes[0].reason).toBe('Released event');
    expect(keyframes[1].frameIndex).toBe(3);
    expect(keyframes[1].reason).toBe('Agent activity');
  });

  test('falls back to the initial frame when nothing meaningful happens', () => {
    const frames = [frame(0), frame(1)];

    const keyframes = deriveReplayKeyframes(frames);

    expect(keyframes).toHaveLength(1);
    expect(keyframes[0].frameIndex).toBe(0);
  });

  test('full-frame mode restores the raw frame sequence', () => {
    const frames = [frame(0), frame(1), frame(2, { agent_cycle_status: 'running' })];
    const keyframes = deriveReplayKeyframes(frames);

    expect(timelineLength(frames, keyframes, 'frames')).toBe(3);
    expect(timelineLength(frames, keyframes, 'actions')).toBe(1);
    expect(frameAtTimelineIndex(frames, keyframes, 'frames', 1)?.index).toBe(1);
    expect(frameAtTimelineIndex(frames, keyframes, 'actions', 0)?.index).toBe(2);
  });

  test('uses demo-friendly fixed delays for action playback speeds', () => {
    expect(replayDelayForSpeed(1)).toBe(1200);
    expect(replayDelayForSpeed(5)).toBe(450);
    expect(replayDelayForSpeed(20)).toBe(120);
  });
});
