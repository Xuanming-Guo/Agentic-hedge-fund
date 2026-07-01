import type { OrderBookSnapshot, PortfolioState } from '../../lib/types';

type Props = {
  portfolio: PortfolioState;
  orderbooks: OrderBookSnapshot[];
};

function pct(value: number) {
  return `${Math.round(value * 100)}%`;
}

function riskFor(book: OrderBookSnapshot, portfolio: PortfolioState) {
  const position = portfolio.positions.find((item) => item.symbol === book.symbol);
  const exposure = Math.abs(position?.market_value ?? 0);
  const exposurePct = exposure / Math.max(1, portfolio.equity);
  const spreadBps = book.mid ? (book.spread / book.mid) * 10000 : 0;
  const imbalance = Math.abs(book.imbalance);
  const lowCash = portfolio.cash / Math.max(1, portfolio.equity) < 0.2;
  const score =
    (exposurePct > 0.15 ? 2 : exposurePct > 0 ? 1 : 0) +
    (spreadBps > 12 ? 2 : spreadBps > 6 ? 1 : 0) +
    (imbalance > 0.25 ? 1 : 0) +
    (lowCash ? 1 : 0);
  const level = score >= 3 ? 'high' : score > 0 ? 'mid' : 'low';
  const reasons = [
    exposurePct > 0 ? `position exposure ${pct(exposurePct)}` : 'no active position',
    `spread ${spreadBps.toFixed(1)} bps`,
    `book imbalance ${pct(imbalance)}`,
    lowCash ? 'cash buffer below 20%' : 'cash buffer healthy'
  ];
  return { level, reasons, exposurePct, spreadBps, imbalance };
}

export function RiskHeatmap({ portfolio, orderbooks }: Props) {
  const cashBuffer = portfolio.cash / Math.max(1, portfolio.equity);
  return (
    <section className="panel span-6">
      <h2>Risk Overview</h2>
      <div className="panel-body risk-overview">
        <div className="risk-summary">
          <div className="stat-row">
            <span>Gross exposure</span>
            <strong>{pct(portfolio.gross_exposure / Math.max(1, portfolio.equity))}</strong>
          </div>
          <div className="stat-row">
            <span>Cash buffer</span>
            <strong>{pct(cashBuffer)}</strong>
          </div>
        </div>
        <div className="risk-list">
          {orderbooks.map((book) => {
            const risk = riskFor(book, portfolio);
            return (
              <article className={`risk-card ${risk.level}`} key={book.symbol}>
                <div className="list-row tight">
                  <strong className="mono">{book.symbol}</strong>
                  <span className={risk.level === 'high' ? 'badge red' : risk.level === 'mid' ? 'badge warning' : 'badge green'}>
                    {risk.level === 'low' ? 'clear' : risk.level}
                  </span>
                </div>
                <p className="muted">{risk.reasons.join(' | ')}</p>
              </article>
            );
          })}
        </div>
      </div>
    </section>
  );
}
