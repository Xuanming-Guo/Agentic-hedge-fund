import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { PortfolioPanel } from './PortfolioPanel';
import type { AgentDecisionTrace, PortfolioState, SimulationSnapshot } from '../../lib/types';

const emptyPortfolio: PortfolioState = {
  cash: 1_000_000,
  equity: 1_000_000,
  realized_pnl: 0,
  unrealized_pnl: 0,
  gross_exposure: 0,
  net_exposure: 0,
  sector_exposure: {},
  positions: []
};

const latestDecision: AgentDecisionTrace = {
  id: 'cycle-1-committee',
  cycle_id: 'cycle-1',
  timestamp: '2026-06-23T14:30:00Z',
  agent_id: 'InvestmentCommitteeChairAgent',
  stage: 'committee',
  symbol: 'TSLA',
  action: 'no_trade',
  requested_quantity: 2825,
  approved_quantity: 0,
  filled_quantity: 0,
  price: 227.04,
  status: 'no_trade',
  rationale: 'Disagreement remains high and expected edge is weak.',
  evidence_ids: [],
  tool_call_ids: []
};

const recentTrades: SimulationSnapshot['trade_tape'] = [
  {
    id: 'fill-1',
    timestamp: '2026-06-23T14:32:00Z',
    symbol: 'AAPL',
    side: 'buy',
    price: 210.25,
    quantity: 120,
    owner_type: 'hedge_fund'
  },
  {
    id: 'fill-2',
    timestamp: '2026-06-23T14:33:00Z',
    symbol: 'TSLA',
    side: 'sell',
    price: 227.04,
    quantity: 40,
    owner_type: 'hedge_fund'
  }
];

test('renders portfolio empty state with profit chart and latest decision context', () => {
  render(
    <PortfolioPanel
      portfolio={emptyPortfolio}
      history={[
        {
          timestamp: '2026-06-23T14:30:00Z',
          equity: 1_000_000,
          cash: 1_000_000,
          total_pnl: 0,
          realized_pnl: 0,
          unrealized_pnl: 0,
          gross_exposure: 0,
          net_exposure: 0
        }
      ]}
      decisions={[latestDecision]}
      trades={[]}
    />
  );

  expect(screen.getByText('Equity')).toBeInTheDocument();
  expect(screen.getByLabelText('Portfolio profit chart')).toBeInTheDocument();
  expect(screen.getByText('No open positions yet')).toBeInTheDocument();
  expect(screen.getByText(/InvestmentCommitteeChairAgent: no trade/)).toBeInTheDocument();
});

test('renders current positions with market value and pnl', () => {
  render(
    <PortfolioPanel
      portfolio={{
        ...emptyPortfolio,
        cash: 800_000,
        equity: 1_012_500,
        unrealized_pnl: 12_500,
        gross_exposure: 212_500,
        net_exposure: 212_500,
        positions: [
          {
            symbol: 'TSLA',
            quantity: 850,
            average_price: 235,
            market_price: 250,
            market_value: 212_500,
            unrealized_pnl: 12_750
          }
        ]
      }}
      history={[]}
      decisions={[]}
      trades={recentTrades}
    />
  );

  expect(screen.getByText('TSLA')).toBeInTheDocument();
  expect(screen.getByText('Long 850')).toBeInTheDocument();
  expect(screen.getAllByText('$212,500')).toHaveLength(2);
  expect(screen.getByText('Recent fills')).toBeInTheDocument();
  expect(screen.getByText('buy 120 AAPL')).toBeInTheDocument();
  expect(screen.getByText('sell 40 TSLA')).toBeInTheDocument();
});
