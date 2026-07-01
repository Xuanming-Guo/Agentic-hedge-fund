import { BrainCircuit, GitBranch, MessageSquareText } from 'lucide-react';
import { useState } from 'react';
import type { AgentDecisionTrace, AgentState, DebateMessage } from '../../lib/types';

type Props = {
  agents: AgentState[];
  debate: DebateMessage[];
  decisions: AgentDecisionTrace[];
  emptyReason?: string;
};

type Tab = 'states' | 'decisions' | 'debate';

function pct(value: number) {
  return `${Math.round(value * 100)}%`;
}

function cycleIdForDebate(message: DebateMessage) {
  return message.id.replace(/-(bull|bear|neutral)$/i, '');
}

function debateGroups(messages: DebateMessage[]) {
  const groups = new Map<string, DebateMessage[]>();
  for (const message of messages) {
    const cycleId = cycleIdForDebate(message);
    groups.set(cycleId, [...(groups.get(cycleId) ?? []), message]);
  }
  return [...groups.entries()]
    .map(([cycleId, items]) => ({
      cycleId,
      symbol: items.find((item) => item.symbol)?.symbol ?? 'symbol pending',
      timestamp: items[items.length - 1]?.timestamp,
      items: [...items].sort((left, right) => left.agent_id.localeCompare(right.agent_id))
    }))
    .sort((left, right) => new Date(right.timestamp).getTime() - new Date(left.timestamp).getTime());
}

export function AgentWorkbench({ agents, debate, decisions, emptyReason }: Props) {
  const [tab, setTab] = useState<Tab>('states');
  const groupedDebate = debateGroups(debate);

  return (
    <section className="panel span-12 compact-side-panel">
      <h2>Agent Workbench</h2>
      <div className="panel-body compact-workbench-body">
        <div className="segmented">
          <button className={tab === 'states' ? 'active' : ''} onClick={() => setTab('states')}>
            <BrainCircuit size={15} />
            States
          </button>
          <button className={tab === 'decisions' ? 'active' : ''} onClick={() => setTab('decisions')}>
            <GitBranch size={15} />
            Decisions
          </button>
          <button className={tab === 'debate' ? 'active' : ''} onClick={() => setTab('debate')}>
            <MessageSquareText size={15} />
            Debate
          </button>
        </div>

        {tab === 'states' && (
          <div className="timeline workbench-scroll">
            {agents.length === 0 ? (
              <p className="muted">{emptyReason ?? 'Agent cycle has not run yet.'}</p>
            ) : (
              agents.map((agent) => (
                <div className="agent-row" key={agent.agent_id}>
                  <div>
                    <strong>{agent.agent_id}</strong>
                    <span className="muted">{agent.role}</span>
                    <p>{agent.last_action}</p>
                    {agent.target_symbol && (
                      <span className="badge">
                        {agent.target_symbol}
                        {agent.decision ? ` ${agent.decision}` : ''}
                        {agent.quantity ? ` ${agent.quantity.toLocaleString()}` : ''}
                      </span>
                    )}
                  </div>
                  <span className="badge">{pct(agent.confidence)}</span>
                </div>
              ))
            )}
          </div>
        )}

        {tab === 'decisions' && (
          <div className="timeline workbench-scroll">
            {decisions.length === 0 ? (
              <p className="muted">
                {emptyReason ?? 'Decision traces appear after the first decision cycle.'}
              </p>
            ) : (
              decisions.slice(-10).reverse().map((decision) => (
                <div className="agent-row" key={decision.id}>
                  <div>
                    <strong>{decision.agent_id}</strong>
                    <span className="muted">{decision.stage.replace('_', ' ')}</span>
                    <p>{decision.rationale}</p>
                    <span className="badge">
                      {decision.symbol} {decision.action.replace('_', ' ')}
                      {decision.approved_quantity
                        ? ` ${decision.approved_quantity.toLocaleString()}`
                        : decision.requested_quantity
                          ? ` ${decision.requested_quantity.toLocaleString()}`
                          : ''}
                    </span>
                  </div>
                  <span className="badge">{decision.status}</span>
                </div>
              ))
            )}
          </div>
        )}

        {tab === 'debate' && (
          <div className="timeline workbench-scroll">
            {debate.length === 0 ? (
              <p className="muted">{emptyReason ?? 'Debate appears after the first decision cycle.'}</p>
            ) : (
              groupedDebate.map((group) => (
                <article className="debate-cycle-card" key={group.cycleId}>
                  <div className="list-row tight">
                    <strong>{group.symbol}</strong>
                    <span className="badge mono">
                      {new Date(group.timestamp).toLocaleTimeString([], {
                        hour: '2-digit',
                        minute: '2-digit'
                      })}
                    </span>
                  </div>
                  {group.items.map((message) => (
                    <div className="debate-pair-row" key={message.id}>
                      <span className={message.stance === 'bear' ? 'badge warning' : 'badge green'}>
                        {message.stance}
                      </span>
                      <div>
                        <strong>{message.agent_id}</strong>
                        <p>{message.message}</p>
                        {message.evidence_ids.length > 0 && (
                          <span className="muted">{message.evidence_ids.join(', ')}</span>
                        )}
                      </div>
                    </div>
                  ))}
                </article>
              ))
            )}
          </div>
        )}

      </div>
    </section>
  );
}
