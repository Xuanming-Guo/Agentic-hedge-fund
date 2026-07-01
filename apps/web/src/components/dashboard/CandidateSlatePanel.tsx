import { ListChecks, TrendingDown, TrendingUp } from 'lucide-react';
import type { AgentDecisionTrace, CandidateSlateItem } from '../../lib/types';

type Props = {
  candidates?: CandidateSlateItem[];
  decisions: AgentDecisionTrace[];
};

function sideIcon(side: CandidateSlateItem['side_hint']) {
  if (side === 'buy') return <TrendingUp size={14} />;
  if (side === 'sell') return <TrendingDown size={14} />;
  return <ListChecks size={14} />;
}

function sideClass(side: CandidateSlateItem['side_hint']) {
  if (side === 'buy') return 'badge green';
  if (side === 'sell') return 'badge warning';
  return 'badge';
}

function roleLabel(role: CandidateSlateItem['allocation_role']) {
  if (role === 'relative_value') return 'relative value';
  return role;
}

function roleClass(role: CandidateSlateItem['allocation_role']) {
  if (role === 'primary') return 'badge green';
  if (role === 'hedge') return 'badge warning';
  if (role === 'relative_value') return 'badge blue';
  return 'badge';
}

function pct(value: number) {
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
}

function latestAllocationSummary(decisions: AgentDecisionTrace[]) {
  const latestCycle = decisions.length ? decisions[decisions.length - 1].cycle_id : null;
  if (!latestCycle) return null;
  const cycleDecisions = decisions.filter((decision) => decision.cycle_id === latestCycle);
  const proposals = cycleDecisions.filter((decision) => decision.stage === 'proposal');
  const routed = cycleDecisions.filter((decision) => ['committee', 'broker', 'fill'].includes(decision.stage));
  if (proposals.length === 0) return null;
  const proposedText = proposals
    .slice(0, 3)
    .map((decision) => `${decision.action} ${decision.symbol}`)
    .join(', ');
  return {
    proposedText,
    routedCount: routed.length
  };
}

export function CandidateSlatePanel({ candidates = [], decisions }: Props) {
  const visible = candidates.slice(0, 10);
  const summary = latestAllocationSummary(decisions);

  return (
    <section className="panel span-12 candidate-slate-panel">
      <h2>Candidate Slate</h2>
      <div className="panel-body candidate-slate-body">
        <div className="candidate-slate-summary">
          <div>
            <span className="muted">Portfolio construction</span>
            <strong>
              {visible.length
                ? `${visible.length} active tickers ranked for basket selection`
                : 'Waiting for the first portfolio slate'}
            </strong>
          </div>
          {summary && (
            <span className="badge">
              latest basket: {summary.proposedText}
              {summary.routedCount ? `, ${summary.routedCount} routed checks` : ''}
            </span>
          )}
        </div>

        {visible.length === 0 ? (
          <p className="muted">The fund will rank all active tickers once an agent cycle completes.</p>
        ) : (
          <div className="candidate-slate-grid" role="table" aria-label="Ranked candidate slate">
            <div className="candidate-slate-head" role="row">
              <span>Rank</span>
              <span>Ticker</span>
              <span>Role</span>
              <span>Signal</span>
              <span>Score</span>
              <span>Features</span>
              <span>Portfolio notes</span>
            </div>
            {visible.map((candidate) => (
              <article className="candidate-slate-row" key={candidate.symbol} role="row">
                <span className="mono">#{candidate.rank}</span>
                <strong>{candidate.symbol}</strong>
                <span className={roleClass(candidate.allocation_role)}>
                  {roleLabel(candidate.allocation_role)}
                </span>
                <span className={sideClass(candidate.side_hint)}>
                  {sideIcon(candidate.side_hint)}
                  {candidate.side_hint}
                </span>
                <strong>{Math.round(candidate.score * 100)}%</strong>
                <span className="candidate-feature-line">
                  {pct(candidate.recent_return_pct)} ret, {candidate.volume_ratio.toFixed(2)}x vol,{' '}
                  {candidate.spread_bps.toFixed(0)} bps spr
                </span>
                <span
                  className="candidate-notes"
                  title={[candidate.hold_reason, ...candidate.relation_notes].filter(Boolean).join(' | ')}
                >
                  {candidate.hold_reason ? `Hold: ${candidate.hold_reason}. ` : ''}
                  {candidate.reason}
                  {candidate.relation_notes.length ? ` | ${candidate.relation_notes[0]}` : ''}
                </span>
              </article>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
