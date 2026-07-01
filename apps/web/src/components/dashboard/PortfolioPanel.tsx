import { LineChart, Scale, ShoppingCart, Wallet } from 'lucide-react';
import type { AgentDecisionTrace, PortfolioHistoryPoint, PortfolioState, SimulationSnapshot } from '../../lib/types';

type Props = {
  portfolio: PortfolioState;
  history?: PortfolioHistoryPoint[];
  decisions: AgentDecisionTrace[];
  trades: SimulationSnapshot['trade_tape'];
};

const chartWidth = 420;
const chartHeight = 150;
const chartPadding = { top: 16, right: 18, bottom: 20, left: 18 };

function money(value: number, digits = 0) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: digits
  }).format(value);
}

function signedMoney(value: number) {
  const formatted = money(Math.abs(value));
  if (value > 0) return `+${formatted}`;
  if (value < 0) return `-${formatted}`;
  return formatted;
}

function pct(value: number) {
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
}

function chartPath(points: PortfolioHistoryPoint[]) {
  const values = points.map((point) => point.total_pnl);
  const minValue = Math.min(...values, 0);
  const maxValue = Math.max(...values, 0);
  const range = maxValue === minValue ? 1 : maxValue - minValue;
  const plotWidth = chartWidth - chartPadding.left - chartPadding.right;
  const plotHeight = chartHeight - chartPadding.top - chartPadding.bottom;

  return points
    .map((point, index) => {
      const x =
        chartPadding.left + (index / Math.max(1, points.length - 1)) * plotWidth;
      const y =
        chartPadding.top + ((maxValue - point.total_pnl) / range) * plotHeight;
      return `${index === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(' ');
}

function baselineY(points: PortfolioHistoryPoint[]) {
  const values = points.map((point) => point.total_pnl);
  const minValue = Math.min(...values, 0);
  const maxValue = Math.max(...values, 0);
  const range = maxValue === minValue ? 1 : maxValue - minValue;
  const plotHeight = chartHeight - chartPadding.top - chartPadding.bottom;
  return chartPadding.top + ((maxValue - 0) / range) * plotHeight;
}

function latestTradeDecision(decisions: AgentDecisionTrace[]) {
  return [...decisions]
    .reverse()
    .find((decision) =>
      ['committee', 'broker', 'fill', 'proposal'].includes(decision.stage)
    );
}

export function PortfolioPanel({ portfolio, history = [], decisions, trades }: Props) {
  const latestHistoryPoint = history[history.length - 1];
  const totalPnl = latestHistoryPoint?.total_pnl ?? portfolio.realized_pnl + portfolio.unrealized_pnl;
  const basis = Math.max(1, history[0]?.equity ?? portfolio.equity - totalPnl);
  const returnPct = (totalPnl / basis) * 100;
  const chartPoints =
    history.length > 1
      ? history.slice(-120)
      : [
          {
            timestamp: new Date().toISOString(),
            equity: basis,
            cash: basis,
            total_pnl: 0,
            realized_pnl: 0,
            unrealized_pnl: 0,
            gross_exposure: 0,
            net_exposure: 0
          },
          {
            timestamp: new Date().toISOString(),
            equity: portfolio.equity,
            cash: portfolio.cash,
            total_pnl: totalPnl,
            realized_pnl: portfolio.realized_pnl,
            unrealized_pnl: portfolio.unrealized_pnl,
            gross_exposure: portfolio.gross_exposure,
            net_exposure: portfolio.net_exposure
          }
        ];
  const latestDecision = latestTradeDecision(decisions);
  const performanceClass = totalPnl >= 0 ? 'portfolio-positive' : 'portfolio-negative';
  const recentTrades = trades.slice(-4).reverse();

  return (
    <section className="panel span-4 portfolio-panel">
      <h2>Portfolio</h2>
      <div className="panel-body portfolio-body">
        <div className="portfolio-hero">
          <div>
            <span className="muted">Equity</span>
            <strong>{money(portfolio.equity)}</strong>
          </div>
          <div className={performanceClass}>
            <span>{signedMoney(totalPnl)}</span>
            <strong>{pct(returnPct)}</strong>
          </div>
        </div>

        <div className="portfolio-chart" aria-label="Portfolio profit chart">
          <svg viewBox={`0 0 ${chartWidth} ${chartHeight}`} role="img">
            <rect width={chartWidth} height={chartHeight} rx="6" fill="#071023" />
            <line
              x1={chartPadding.left}
              x2={chartWidth - chartPadding.right}
              y1={baselineY(chartPoints)}
              y2={baselineY(chartPoints)}
              stroke="#31466f"
              strokeDasharray="4 4"
            />
            <path
              d={chartPath(chartPoints)}
              fill="none"
              stroke={totalPnl >= 0 ? '#35d391' : '#ff5c7a'}
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="3"
            />
          </svg>
        </div>

        <div className="portfolio-stats">
          <div>
            <Wallet size={14} />
            <span>Cash</span>
            <strong>{money(portfolio.cash)}</strong>
          </div>
          <div>
            <LineChart size={14} />
            <span>Unrealized</span>
            <strong>{signedMoney(portfolio.unrealized_pnl)}</strong>
          </div>
          <div>
            <Scale size={14} />
            <span>Exposure</span>
            <strong>{money(portfolio.gross_exposure)}</strong>
          </div>
        </div>

        <div className="portfolio-positions">
          <div className="list-row tight">
            <span className="muted">Current positions</span>
            <strong>{portfolio.positions.length}</strong>
          </div>
          {portfolio.positions.length === 0 ? (
            <div className="portfolio-empty">
              <strong>No open positions yet</strong>
              <span className="muted">
                {latestDecision
                  ? `${latestDecision.agent_id}: ${latestDecision.status.replace('_', ' ')} - ${latestDecision.rationale}`
                  : 'The portfolio will populate after an approved simulated fill.'}
              </span>
            </div>
          ) : (
            portfolio.positions.map((position) => (
              <article className="portfolio-position-card" key={position.symbol}>
                <div>
                  <strong>{position.symbol}</strong>
                  <span className="muted">
                    {position.quantity > 0 ? 'Long' : 'Short'} {Math.abs(position.quantity).toLocaleString()}
                  </span>
                </div>
                <div>
                  <span className="muted">Avg / Mkt</span>
                  <strong>
                    {money(position.average_price, 2)} / {money(position.market_price, 2)}
                  </strong>
                </div>
                <div>
                  <span className="muted">Value</span>
                  <strong>{money(position.market_value)}</strong>
                </div>
                <div className={position.unrealized_pnl >= 0 ? 'portfolio-positive' : 'portfolio-negative'}>
                  <span className="muted">P/L</span>
                  <strong>{signedMoney(position.unrealized_pnl)}</strong>
                </div>
              </article>
            ))
          )}
        </div>

        <div className="portfolio-fills">
          <div className="list-row tight">
            <span className="muted">Recent fills</span>
            <strong>{recentTrades.length}</strong>
          </div>
          {recentTrades.length === 0 ? (
            <span className="muted">none</span>
          ) : (
            <div className="portfolio-fill-list">
              {recentTrades.map((trade) => (
                <span className="badge green" key={trade.id}>
                  <ShoppingCart size={13} />
                  {trade.side} {trade.quantity.toLocaleString()} {trade.symbol}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
