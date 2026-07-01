import { fireEvent, render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { CandlestickChart } from './CandlestickChart';
import type { MarketBar } from '../../lib/types';

function bars(count: number): MarketBar[] {
  return Array.from({ length: count }, (_, index) => {
    const open = 100 + index * 0.1;
    const close = open + (index % 2 === 0 ? 0.4 : -0.25);
    return {
      symbol: 'AAPL',
      timestamp: new Date(Date.UTC(2026, 5, 23, 13, 30 + index)).toISOString(),
      open,
      high: Math.max(open, close) + 0.2,
      low: Math.min(open, close) - 0.2,
      close,
      volume: 100_000 + index
    };
  });
}

test('supports zoom, wheel pan, drag pan, and reset view', () => {
  render(<CandlestickChart bars={bars(120)} symbol="AAPL" />);

  expect(screen.getByText('Candles 25-120 / 120')).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Zoom in candles' }));
  expect(screen.getByText('Candles 49-120 / 120')).toBeInTheDocument();

  const chart = screen.getByRole('img', { name: 'AAPL candlestick chart' });
  const wheel = new WheelEvent('wheel', { bubbles: true, cancelable: true, deltaY: 120 });
  fireEvent(chart, wheel);
  expect(wheel.defaultPrevented).toBe(true);
  expect(screen.queryByText('Candles 49-120 / 120')).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Zoom in candles' }));
  const beforeDrag = screen.getByText(/Candles/).textContent;
  fireEvent.mouseDown(chart, { clientX: 420 });
  fireEvent.mouseMove(chart, { clientX: 560 });
  fireEvent.mouseUp(chart);
  expect(screen.getByText(/Candles/).textContent).not.toBe(beforeDrag);

  fireEvent.click(screen.getByRole('button', { name: 'Reset candle view' }));
  expect(screen.getByText('Candles 25-120 / 120')).toBeInTheDocument();
});
