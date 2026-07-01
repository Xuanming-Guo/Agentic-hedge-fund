import type {
  AgentState,
  CommitteeDecision,
  ConsensusSnapshot,
  DebateMessage,
  ConflictRecord
} from '../../lib/types';

type Props = {
  decisions: CommitteeDecision[];
  consensus: ConsensusSnapshot[];
  conflicts: ConflictRecord[];
  agents: AgentState[];
  debate: DebateMessage[];
  className?: string;
};

const BULLISH = new Set(['bullish', 'bull', 'buy', 'long']);
const BEARISH = new Set(['bearish', 'bear', 'sell', 'short']);
const NEUTRAL = new Set(['neutral', 'hold', 'monitor', 'no_trade']);
const PROCEDURAL_AGENTS = new Set([
  'CoordinatorAgent',
  'RiskManagerAgent',
  'ComplianceOfficerAgent',
  'InvestmentCommitteeChairAgent',
  'ExecutionTraderAgent'
]);

function sideFor(value?: string | null) {
  const normalized = value?.toLowerCase().replace('-', '_');
  if (!normalized) return null;
  if (BULLISH.has(normalized)) return 'bullish';
  if (BEARISH.has(normalized)) return 'bearish';
  if (NEUTRAL.has(normalized)) return 'neutral';
  return null;
}

function agentLabel(agentId: string) {
  return agentId.replace(/Agent$/, '').replace(/([a-z])([A-Z])/g, '$1 $2');
}

function pct(value?: number) {
  if (value === undefined) return null;
  return `${Math.round(value * 100)}%`;
}

function consensusAlignment(
  consensus: ConsensusSnapshot | undefined,
  agents: AgentState[],
  debate: DebateMessage[]
) {
  const direction = sideFor(consensus?.consensus_direction);
  if (!direction) return { agree: [], disagree: [] };
  const debateByAgent = new Map(debate.map((message) => [message.agent_id, message.stance]));
  const rows = agents
    .map((agent) => {
      const stance = sideFor(debateByAgent.get(agent.agent_id) ?? agent.decision);
      if (!stance) return null;
      if (PROCEDURAL_AGENTS.has(agent.agent_id) && !['buy', 'sell', 'hold'].includes(agent.decision ?? '')) {
        return null;
      }
      return {
        agentId: agent.agent_id,
        label: agentLabel(agent.agent_id),
        stance,
        rawStance: debateByAgent.get(agent.agent_id) ?? agent.decision ?? stance,
        confidence: pct(agent.confidence)
      };
    })
    .filter((item): item is NonNullable<typeof item> => Boolean(item));
  return {
    agree: rows.filter((row) => row.stance === direction),
    disagree: rows.filter((row) => row.stance !== direction)
  };
}

export function InvestmentCommitteeBoard({
  decisions,
  consensus,
  conflicts,
  agents,
  debate,
  className = 'span-6'
}: Props) {
  const latest = decisions[decisions.length - 1];
  const latestConsensus = consensus[consensus.length - 1];
  const latestConflict = conflicts[conflicts.length - 1];
  const alignment = consensusAlignment(latestConsensus, agents, debate);

  return (
    <section className={`panel ${className}`}>
      <h2>Investment Committee</h2>
      <div className="panel-body">
        {latest ? (
          <>
            <div className="stat-row">
              <span>{latest.symbol}</span>
              <strong>{latest.approved_action} / {latest.final_decision.replace('_', ' ')}</strong>
            </div>
            <div className="stat-row">
              <span>Approved quantity</span>
              <span className="mono">{latest.approved_quantity.toLocaleString()}</span>
            </div>
            <div className="stat-row">
              <span>Approved notional</span>
              <span className="mono">
                {new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(latest.approved_notional)}
              </span>
            </div>
            <div className="stat-row">
              <span>Order style</span>
              <span>{latest.required_order_style}</span>
            </div>
            <p className="muted">{latest.primary_reason}</p>
            <div className="toolbar">
              {latest.risk_constraints_applied.map((constraint) => (
                <span className="badge warning" key={constraint}>{constraint}</span>
              ))}
              {latest.compliance_constraints_applied.map((constraint) => (
                <span className="badge red" key={constraint}>{constraint}</span>
              ))}
              {latest.execution_constraints_applied.map((constraint) => (
                <span className="badge" key={constraint}>{constraint}</span>
              ))}
            </div>
            {latest.dissenting_views.map((view) => (
              <p key={view} className="badge warning">
                {view}
              </p>
            ))}
          </>
        ) : (
          <p className="muted">Awaiting first committee decision.</p>
        )}
        {latestConsensus && (
          <>
            <div className="split">
              <div className="stat-row">
                <span>Consensus</span>
                <strong>{Math.round(latestConsensus.consensus_strength * 100)}%</strong>
              </div>
              <div className="stat-row">
                <span>Disagreement</span>
                <strong>{Math.round(latestConsensus.disagreement_score * 100)}%</strong>
              </div>
            </div>
            <div className="alignment-block">
              <span className="muted">Agree</span>
              <div className="toolbar">
                {alignment.agree.length === 0 ? (
                  <span className="badge">none</span>
                ) : (
                  alignment.agree.map((agent) => (
                    <span className="badge green" key={`agree-${agent.agentId}`}>
                      {agent.label}: {agent.rawStance}
                      {agent.confidence ? ` ${agent.confidence}` : ''}
                    </span>
                  ))
                )}
              </div>
              <span className="muted">Disagree</span>
              <div className="toolbar">
                {alignment.disagree.length === 0 ? (
                  <span className="badge">none</span>
                ) : (
                  alignment.disagree.map((agent) => (
                    <span className="badge warning" key={`disagree-${agent.agentId}`}>
                      {agent.label}: {agent.rawStance}
                      {agent.confidence ? ` ${agent.confidence}` : ''}
                    </span>
                  ))
                )}
              </div>
            </div>
          </>
        )}
        {latestConflict && <p className="muted">{latestConflict.winning_constraint}: {latestConflict.final_decision}</p>}
      </div>
    </section>
  );
}
