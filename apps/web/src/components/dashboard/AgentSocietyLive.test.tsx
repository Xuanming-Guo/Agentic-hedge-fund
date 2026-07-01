import { fireEvent, render, screen, within } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import { AgentSocietyLive } from './AgentSocietyLive';
import type { AgentActivityDetail, SimulationSnapshot } from '../../lib/types';

const snapshot: SimulationSnapshot = {
  simulation_id: 'sim-1',
  scenario: {
    id: 'scenario-1',
    display_date: '2026-06-23',
    title: 'Test scenario',
    description: 'Test scenario',
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
    depth_source: 'synthetic',
    requested_tickers: [],
    active_tickers: [],
    replay_date: '2026-06-23',
    warning: null
  },
  status: 'running',
  current_time: '2026-06-23T14:30:00Z',
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
  agent_states: [],
  debate: [],
  conflicts: [],
  agent_decisions: [],
  committee_decisions: [],
  consensus: [],
  skill_calls: [],
  agent_activity_feed: [
    {
      id: 'activity-1',
      timestamp: '2026-06-23T14:30:00Z',
      cycle_id: 'cycle-1',
      kind: 'agent_completed',
      agent_id: 'MacroAnalystAgent',
      title: 'AI output normalized',
      message: 'Normalized AI JSON to match the expected agent schema.',
      symbol: 'AAPL',
      status: 'complete',
      provider: 'qwen',
      model: 'qwen-plus',
      repair_status: 'normalized',
      validation_summary: 'Normalized AI JSON to match the expected agent schema.',
      evidence_ids: [],
      tool_call_ids: []
    }
  ],
  benchmark: null,
  agent_cycle_status: 'complete',
  active_cycle_id: null,
  active_agent: null,
  active_provider: 'qwen',
  configured_provider: 'qwen',
  completed_llm_calls: 6,
  expected_llm_calls: 6,
  last_llm_error: null,
  last_llm_provider: 'qwen',
  last_completed_provider: 'qwen',
  last_fallback_provider: null,
  last_fallback_agent: null,
  last_fallback_reason: null,
  last_llm_model: 'qwen-plus',
  last_llm_calls: 6,
  last_llm_tokens: 1200
};

const detail: AgentActivityDetail = {
  activity_id: 'activity-1',
  overview: {
    title: 'AI output normalized',
    message: 'Normalized AI JSON to match the expected agent schema.',
    reasoning_summary: 'Normalized AI JSON to match the expected agent schema.'
  },
  input: {},
  output: {
    message: 'Normalized AI JSON to match the expected agent schema.',
    raw_structured_output: '{\n  "action": "no_action",\n  "key_drivers": ["neutral_sentiment"]\n}',
    validated_json: {
      agent_id: 'MacroAnalystAgent',
      symbol: 'AAPL',
      direction: 'neutral'
    }
  },
  references: [],
  validation: {},
  metrics: {}
};

test('formats nested raw structured output as parsed JSON in the chat detail panel', async () => {
  const load = vi.fn(() => Promise.resolve(detail));

  render(<AgentSocietyLive snapshot={snapshot} activityDetailLoader={{ load }} />);

  fireEvent.click(screen.getByRole('button', { name: /Open chat/i }));
  fireEvent.click(await screen.findByRole('button', { name: 'Outputs' }));

  const parsedBlock = screen.getByText('Raw structured output (parsed)').closest('.json-block');
  expect(parsedBlock).not.toBeNull();
  const parsedPre = within(parsedBlock as HTMLElement).getByText((_, node) =>
    Boolean(node?.tagName.toLowerCase() === 'pre' && node.textContent?.includes('"action": "no_action"'))
  );
  expect(parsedPre).toBeInTheDocument();
  expect(screen.getByText('Raw structured output (original)')).toBeInTheDocument();
  expect(screen.getByText('Validated JSON')).toBeInTheDocument();
  expect(screen.queryByText(/qwen|qwen-plus|mock/i)).not.toBeInTheDocument();
});
