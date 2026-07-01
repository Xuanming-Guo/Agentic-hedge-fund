import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { CandidateSlatePanel } from './CandidateSlatePanel';
import type { AgentDecisionTrace, CandidateSlateItem } from '../../lib/types';

const candidates: CandidateSlateItem[] = [
  {
    symbol: 'TSLA',
    rank: 1,
    score: 0.84,
    side_hint: 'buy',
    allocation_role: 'primary',
    hold_reason: null,
    reason: 'event score 0.80; return 1.20%; volume 1.55x; imbalance 0.18',
    event_ids: ['event-1'],
    event_count: 1,
    latest_price: 227.04,
    recent_return_pct: 1.2,
    volatility_pct: 0.42,
    volume_ratio: 1.55,
    spread_bps: 8,
    orderbook_imbalance: 0.18,
    sector: 'Consumer',
    current_position: 0,
    relation_notes: ['top relative momentum in active slate']
  },
  {
    symbol: 'AMD',
    rank: 2,
    score: 0.72,
    side_hint: 'sell',
    allocation_role: 'hedge',
    hold_reason: null,
    reason: 'event score 0.60; return -0.80%; volume 1.20x; imbalance -0.15',
    event_ids: ['event-2'],
    event_count: 1,
    latest_price: 121.03,
    recent_return_pct: -0.8,
    volatility_pct: 0.38,
    volume_ratio: 1.2,
    spread_bps: 11,
    orderbook_imbalance: -0.15,
    sector: 'Semiconductors',
    current_position: 0,
    relation_notes: ['sector Semiconductors exposure $0']
  },
  {
    symbol: 'AMZN',
    rank: 3,
    score: 0.6,
    side_hint: 'buy',
    allocation_role: 'relative_value',
    hold_reason: null,
    reason: 'event score 0.20; return 0.20%; volume 1.05x; imbalance 0.04',
    event_ids: [],
    event_count: 0,
    latest_price: 185,
    recent_return_pct: 0.2,
    volatility_pct: 0.22,
    volume_ratio: 1.05,
    spread_bps: 10,
    orderbook_imbalance: 0.04,
    sector: 'Consumer',
    current_position: 0,
    relation_notes: []
  },
  {
    symbol: 'META',
    rank: 4,
    score: 0.55,
    side_hint: 'hold',
    allocation_role: 'watchlist',
    hold_reason: 'no direct event',
    reason: 'event score 0.00; return 0.18%; volume 0.95x; imbalance 0.01',
    event_ids: [],
    event_count: 0,
    latest_price: 500,
    recent_return_pct: 0.18,
    volatility_pct: 0.24,
    volume_ratio: 0.95,
    spread_bps: 12,
    orderbook_imbalance: 0.01,
    sector: 'Communication Services',
    current_position: 0,
    relation_notes: []
  },
  {
    symbol: 'GOOGL',
    rank: 5,
    score: 0.5,
    side_hint: 'hold',
    allocation_role: 'watchlist',
    hold_reason: 'score too weak',
    reason: 'event score 0.00; return 0.12%; volume 0.90x; imbalance 0.00',
    event_ids: [],
    event_count: 0,
    latest_price: 175,
    recent_return_pct: 0.12,
    volatility_pct: 0.21,
    volume_ratio: 0.9,
    spread_bps: 9,
    orderbook_imbalance: 0,
    sector: 'Communication Services',
    current_position: 0,
    relation_notes: []
  },
  {
    symbol: 'MSFT',
    rank: 6,
    score: 0.41,
    side_hint: 'hold',
    allocation_role: 'watchlist',
    hold_reason: 'sector risk',
    reason: 'event score 0.00; return 0.10%; volume 1.00x; imbalance 0.00',
    event_ids: [],
    event_count: 0,
    latest_price: 420,
    recent_return_pct: 0.1,
    volatility_pct: 0.2,
    volume_ratio: 1,
    spread_bps: 9,
    orderbook_imbalance: 0,
    sector: 'Technology',
    current_position: 0,
    relation_notes: ['sector Technology exposure $0']
  }
];

const decisions: AgentDecisionTrace[] = [
  {
    id: 'cycle-1-proposal-1-TSLA',
    cycle_id: 'cycle-1',
    timestamp: '2026-06-23T14:30:00Z',
    agent_id: 'PortfolioManagerAgent',
    stage: 'proposal',
    symbol: 'TSLA',
    action: 'buy',
    requested_quantity: 850,
    approved_quantity: 0,
    filled_quantity: 0,
    price: null,
    status: 'proposed',
    rationale: 'Ranked first in the slate.',
    evidence_ids: ['event-1'],
    tool_call_ids: []
  }
];

test('renders ranked candidates and latest basket summary', () => {
  render(<CandidateSlatePanel candidates={candidates} decisions={decisions} />);

  expect(screen.getByText('Candidate Slate')).toBeInTheDocument();
  expect(screen.getByText('6 active tickers ranked for basket selection')).toBeInTheDocument();
  expect(screen.getByText('TSLA')).toBeInTheDocument();
  expect(screen.getByText('AMD')).toBeInTheDocument();
  expect(screen.getByText('MSFT')).toBeInTheDocument();
  expect(screen.getByText('84%')).toBeInTheDocument();
  expect(screen.getByText('primary')).toBeInTheDocument();
  expect(screen.getByText('hedge')).toBeInTheDocument();
  expect(screen.getByText('relative value')).toBeInTheDocument();
  expect(screen.getAllByText('watchlist')).toHaveLength(3);
  expect(screen.getByText(/latest basket: buy TSLA/)).toBeInTheDocument();
  expect(screen.getByText(/Hold: no direct event/)).toBeInTheDocument();
  expect(screen.getByText(/top relative momentum/)).toBeInTheDocument();
});
