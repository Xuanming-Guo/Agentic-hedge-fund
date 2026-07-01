import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { OrderBookPanel } from './OrderBookPanel';
import type { OrderBookSnapshot } from '../../lib/types';

test('renders order book participants as a comma-separated summary cell', () => {
  const orderbook: OrderBookSnapshot = {
    symbol: 'ALPH',
    bids: [],
    asks: [
      {
        price: 121.28,
        quantity: 1927,
        order_count: 7,
        participants: [
          { owner_type: 'background_market_maker', order_count: 2, quantity: 582 },
          { owner_type: 'dark_pool_proxy', order_count: 1, quantity: 137 },
          { owner_type: 'institutional_liquidity', order_count: 2, quantity: 312 },
          { owner_type: 'retail_lot', order_count: 1, quantity: 114 },
          { owner_type: 'hedge_fund', order_count: 1, quantity: 42 }
        ]
      }
    ],
    mid: 121.03,
    spread: 0.04,
    imbalance: 0.12,
    last_trade: null
  };

  render(<OrderBookPanel orderbooks={[orderbook]} trades={[]} />);

  const summary = screen.getByText('MM 582, DARK 137, INST 312, +156');
  expect(summary).toHaveTextContent('MM 582, DARK 137, INST 312, +156');
  expect(summary).toHaveAttribute('title', expect.stringContaining('RTL: 114 shares across 1 order(s)'));
  expect(summary).toHaveAttribute('title', expect.stringContaining('HF: 42 shares across 1 order(s)'));
  expect(screen.queryByText('RTL 114')).not.toBeInTheDocument();
  expect(screen.getByText('MID')).toBeInTheDocument();
});
