import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { expect, test, vi } from 'vitest';
import App from './App';

test('renders the application shell', () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const snapshot = {
        simulation_id: 'sim-test',
        scenario: { id: '2024-05-10', display_date: '2024-05-10', title: 'Test', description: 'Test', seed: 1, status: 'active' },
        status: 'created',
        current_time: new Date().toISOString(),
        speed: 1,
        released_events: [],
        latest_bars: [],
        history_bars: [],
        orderbooks: [],
        trade_tape: [],
        portfolio: { cash: 1000000, equity: 1000000, realized_pnl: 0, unrealized_pnl: 0, gross_exposure: 0, net_exposure: 0, sector_exposure: {}, positions: [] },
        agent_states: [],
        debate: [],
        conflicts: [],
        agent_decisions: [],
        committee_decisions: [],
        consensus: [],
        skill_calls: [],
        benchmark: null
      };
      return {
        ok: true,
        json: async () => (url.includes('/api/scenarios') ? { scenarios: [] } : snapshot)
      } as Response;
    })
  );
  render(
    <QueryClientProvider client={new QueryClient()}>
      <App />
    </QueryClientProvider>
  );
  expect(screen.getByText('Agentic Hedge Fund')).toBeInTheDocument();
});
