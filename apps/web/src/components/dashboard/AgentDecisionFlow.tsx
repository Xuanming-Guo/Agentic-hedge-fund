import {
  AlertTriangle,
  CheckCircle2,
  CircleSlash,
  GitBranch,
  Scale,
  ShieldCheck,
  TrendingDown,
  TrendingUp
} from 'lucide-react';
import type { AgentDecisionTrace, PortfolioState } from '../../lib/types';

type Props = {
  decisions: AgentDecisionTrace[];
  positions: PortfolioState['positions'];
  emptyReason?: string;
};

function actionIcon(action: string) {
  if (action === 'buy' || action === 'bullish') return <TrendingUp size={15} />;
  if (action === 'sell' || action === 'short' || action === 'bearish') return <TrendingDown size={15} />;
  if (action === 'reject' || action === 'rejected') return <CircleSlash size={15} />;
  if (action.includes('approve') || action === 'filled') return <CheckCircle2 size={15} />;
  if (action.includes('risk') || action.includes('compliance')) return <ShieldCheck size={15} />;
  return <GitBranch size={15} />;
}

function actionClass(trace: AgentDecisionTrace) {
  if (trace.status === 'rejected' || trace.action === 'reject') return 'badge red';
  if (trace.status === 'filled' || trace.action.includes('approve')) return 'badge green';
  if (trace.action === 'short' || trace.action === 'sell' || trace.action === 'bearish') return 'badge warning';
  return 'badge';
}

function quantityText(trace: AgentDecisionTrace) {
  if (trace.filled_quantity) return `filled ${trace.filled_quantity.toLocaleString()}`;
  if (trace.approved_quantity) return `approved ${trace.approved_quantity.toLocaleString()}`;
  if (trace.requested_quantity) return `requested ${trace.requested_quantity.toLocaleString()}`;
  return trace.symbol;
}

function money(value: number | null) {
  if (value === null) return '';
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(value);
}

export function AgentDecisionFlow({ decisions, positions, emptyReason }: Props) {
  const latestCycle = decisions.length ? decisions[decisions.length - 1].cycle_id : null;
  const latest = latestCycle ? decisions.filter((decision) => decision.cycle_id === latestCycle) : [];
  const visible = latest.length ? latest : decisions.slice(-8);
  const cycleProposals = visible.filter((trace) => trace.stage === 'proposal');
  const basketSymbols = Array.from(new Set(cycleProposals.map((trace) => trace.symbol)));

  return (
    <section className="panel span-12">
      <h2>Agent Decision Flow</h2>
      <div className="panel-body">
        {visible.length === 0 ? (
          <p className="muted">
            {emptyReason ?? 'Agent decisions will appear after the first decision cycle.'}
          </p>
        ) : (
          <>
            {cycleProposals.length > 1 && (
              <div className="decision-basket-summary">
                <div>
                  <span className="muted">Portfolio basket</span>
                  <strong>{basketSymbols.join(', ')}</strong>
                </div>
                <span className="badge">
                  {cycleProposals.filter((trace) => trace.action !== 'hold').length} proposed /{' '}
                  {cycleProposals.length} ranked actions
                </span>
              </div>
            )}
            <div className="decision-flow">
              {visible.map((trace) => (
                <article className="decision-node" key={trace.id}>
                  <div className="decision-node-head">
                    <span className="badge">{trace.stage.replace('_', ' ')}</span>
                    <span className={actionClass(trace)}>
                      {actionIcon(trace.action)}
                      {trace.action.replace('_', ' ')}
                    </span>
                  </div>
                  <strong>{trace.agent_id}</strong>
                  <div className="list-row tight">
                    <span className="mono">{trace.symbol}</span>
                    <span>{quantityText(trace)}</span>
                  </div>
                  {trace.price !== null && <span className="muted mono">{money(trace.price)}</span>}
                  <p>{trace.rationale}</p>
                </article>
              ))}
            </div>
            <div className="decision-summary">
              <div>
                <span className="muted">Open positions</span>
                {positions.length === 0 ? (
                  <strong>none</strong>
                ) : (
                  positions.map((position) => (
                    <span className="badge" key={position.symbol}>
                      <Scale size={13} />
                      {position.symbol} {position.quantity < 0 ? 'short' : 'long'} {Math.abs(position.quantity).toLocaleString()}
                    </span>
                  ))
                )}
              </div>
              {visible.some((trace) => trace.status === 'rejected') && (
                <span className="badge red">
                  <AlertTriangle size={13} />
                  broker or compliance blocked an action
                </span>
              )}
            </div>
          </>
        )}
      </div>
    </section>
  );
}
