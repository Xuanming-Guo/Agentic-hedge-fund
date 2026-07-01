import { useEffect, useMemo, useState } from 'react';
import type { OrderBookSnapshot, SimulationSnapshot } from '../../lib/types';

type Props = {
  orderbooks: OrderBookSnapshot[];
  trades: SimulationSnapshot['trade_tape'];
};

type Level = OrderBookSnapshot['bids'][number];

function latestTradeFor(symbol: string, trades: SimulationSnapshot['trade_tape']) {
  return [...trades].reverse().find((trade) => trade.symbol === symbol);
}

function priceLabel(value?: number) {
  return value === undefined ? '-' : value.toFixed(2);
}

function pct(value: number) {
  return `${Math.round(value * 100)}%`;
}

function participantLabel(ownerType: string) {
  if (ownerType === 'hedge_fund') return 'HF';
  if (ownerType === 'background_market_maker') return 'MM';
  if (ownerType === 'institutional_liquidity') return 'INST';
  if (ownerType === 'retail_lot') return 'RTL';
  if (ownerType === 'dark_pool_proxy') return 'DARK';
  if (ownerType === 'aggregate') return 'AGG';
  return ownerType.replace(/_/g, ' ');
}

function participantsFor(level: Level) {
  if (level.participants && level.participants.length > 0) return level.participants;
  return [
    {
      owner_type: 'aggregate',
      order_count: level.order_count ?? 1,
      quantity: level.quantity
    }
  ];
}

function participantTitle(participant: ReturnType<typeof participantsFor>[number]) {
  return `${participantLabel(participant.owner_type)}: ${participant.quantity.toLocaleString()} shares across ${participant.order_count.toLocaleString()} order(s)`;
}

function participantSummaryFor(level: Level) {
  const participants = participantsFor(level);
  const visible = participants.slice(0, 3);
  const hidden = participants.slice(3);
  const hiddenQuantity = hidden.reduce((total, participant) => total + participant.quantity, 0);
  const visibleLabels = visible.map(
    (participant) => `${participantLabel(participant.owner_type)} ${participant.quantity.toLocaleString()}`
  );
  if (hidden.length > 0) {
    visibleLabels.push(`+${hiddenQuantity.toLocaleString()}`);
  }
  return {
    label: visibleLabels.join(', '),
    title: participants.map(participantTitle).join('\n')
  };
}

export function OrderBookPanel({ orderbooks, trades }: Props) {
  const [selectedSymbol, setSelectedSymbol] = useState(orderbooks[0]?.symbol ?? 'ALPH');
  const selectedBook = orderbooks.find((book) => book.symbol === selectedSymbol) ?? orderbooks[0];
  const latestTrade = selectedBook ? latestTradeFor(selectedBook.symbol, trades) : undefined;
  const levels = useMemo(() => {
    if (!selectedBook) return [];
    return [...selectedBook.bids, ...selectedBook.asks];
  }, [selectedBook]);
  const maxQuantity = Math.max(1, ...levels.map((level) => level.quantity));
  const bidQuantity = selectedBook?.bids.reduce((total, level) => total + level.quantity, 0) ?? 0;
  const askQuantity = selectedBook?.asks.reduce((total, level) => total + level.quantity, 0) ?? 0;

  useEffect(() => {
    if (selectedBook) return;
    setSelectedSymbol(orderbooks[0]?.symbol ?? 'ALPH');
  }, [orderbooks, selectedBook]);

  if (!selectedBook) {
    return (
      <section className="panel span-8">
        <h2>Order Book</h2>
        <div className="panel-body">
          <p className="muted">Order book appears once market data is available.</p>
        </div>
      </section>
    );
  }

  function renderLevel(level: Level, side: 'ask' | 'bid') {
    const hit = latestTrade && Math.abs(latestTrade.price - level.price) < 0.005;
    const participants = participantSummaryFor(level);
    return (
      <div
        className={`big-book-level ${side} ${hit ? 'hit' : ''}`}
        key={`${side}-${level.price}-${hit ? latestTrade?.id : 'resting'}`}
      >
        <span className="mono book-price">{priceLabel(level.price)}</span>
        <div className="big-book-depth">
          <span style={{ width: `${Math.max(6, (level.quantity / maxQuantity) * 100)}%` }} />
        </div>
        <span className="mono book-size">{level.quantity.toLocaleString()}</span>
        <span className="mono book-orders">{level.order_count ?? participantsFor(level).length}</span>
        <div className="book-participants">
          <span className="book-participant-list" title={participants.title}>
            {participants.label}
          </span>
        </div>
      </div>
    );
  }

  return (
    <section className="panel span-8 orderbook-panel">
      <h2>Order Book</h2>
      <div className="panel-body big-book">
        <div className="list-row tight">
          <span className="badge">{selectedBook.market_data_mode ?? 'synthetic'}</span>
          <span className="badge">{selectedBook.feed ?? 'synthetic'}</span>
          <span className="badge">{selectedBook.depth_source ?? 'generated depth'}</span>
        </div>
        <div className="book-tabs" role="tablist" aria-label="Order book ticker">
          {orderbooks.map((book) => (
            <button
              className={book.symbol === selectedBook.symbol ? 'active' : ''}
              key={book.symbol}
              onClick={() => setSelectedSymbol(book.symbol)}
              role="tab"
              type="button"
            >
              <strong>{book.symbol}</strong>
              <span>spr {book.spread.toFixed(2)}</span>
            </button>
          ))}
        </div>

        <div className="big-book-head">
          <div>
            <span className="muted">Selected ticker</span>
            <strong className="mono">{selectedBook.symbol}</strong>
          </div>
          <div>
            <span className="muted">Mid</span>
            <strong className="mono">{selectedBook.mid.toFixed(2)}</strong>
          </div>
          <div>
            <span className="muted">Spread</span>
            <strong className="mono">{selectedBook.spread.toFixed(2)}</strong>
          </div>
          <div>
            <span className="muted">Imbalance</span>
            <strong className={selectedBook.imbalance >= 0 ? 'mono positive-text' : 'mono negative-text'}>
              {pct(selectedBook.imbalance)}
            </strong>
          </div>
          <div>
            <span className="muted">Depth</span>
            <strong className="mono">
              {bidQuantity.toLocaleString()} / {askQuantity.toLocaleString()}
            </strong>
          </div>
        </div>

        <div className="big-book-ladder">
          <div className="big-book-row-labels">
            <span>Price</span>
            <span>Depth</span>
            <span>Qty</span>
            <span>Orders</span>
            <span>Participants</span>
          </div>
          {[...selectedBook.asks].reverse().map((level) => renderLevel(level, 'ask'))}
          <div className={`big-book-mid ${latestTrade ? 'pulse' : ''}`}>
            <div className="big-book-mid-marker">
              <span>MID</span>
              <strong className="mono">{selectedBook.mid.toFixed(2)}</strong>
            </div>
            {latestTrade ? (
              <span className="big-book-mid-status">
                last hit {latestTrade.side} {latestTrade.quantity.toLocaleString()} @ {latestTrade.price.toFixed(2)}
              </span>
            ) : (
              <span className="big-book-mid-status">no hedge-fund fill yet</span>
            )}
          </div>
          {selectedBook.bids.map((level) => renderLevel(level, 'bid'))}
        </div>
      </div>
    </section>
  );
}
