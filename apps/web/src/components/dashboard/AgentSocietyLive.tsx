import {
  AlertTriangle,
  BrainCircuit,
  CheckCircle2,
  CircleSlash,
  GitBranch,
  Maximize2,
  MessageSquareText,
  ShieldCheck,
  ShoppingCart,
  Wrench,
  X
} from 'lucide-react';
import { useEffect, useMemo, useState, type Dispatch, type SetStateAction } from 'react';
import { getAgentActivityDetail } from '../../lib/api';
import type { AgentActivityDetail, AgentActivityItem, SimulationSnapshot } from '../../lib/types';

type Props = {
  snapshot: SimulationSnapshot;
  emptyReason?: string;
  activityDetailLoader?: {
    load: CallableFunction;
  };
};

type DetailTab = 'overview' | 'inputs' | 'outputs' | 'references' | 'validation';

const detailTabs: DetailTab[] = ['overview', 'inputs', 'outputs', 'references', 'validation'];

function activityIcon(kind: AgentActivityItem['kind'], status?: string | null) {
  if (kind === 'error' || status === 'rejected') return <AlertTriangle size={15} />;
  if (kind === 'tool_call') return <Wrench size={15} />;
  if (kind === 'risk_review' || kind === 'compliance_review') return <ShieldCheck size={15} />;
  if (kind === 'committee_decision') return <GitBranch size={15} />;
  if (kind === 'broker_route' || kind === 'fill') return <ShoppingCart size={15} />;
  if (kind === 'agent_completed') return <CheckCircle2 size={15} />;
  if (status === 'defer' || status === 'no_trade') return <CircleSlash size={15} />;
  return <BrainCircuit size={15} />;
}

function activityClass(item: AgentActivityItem) {
  if (item.kind === 'error' || item.status === 'rejected') return 'chat-bubble warning';
  if (item.kind === 'fill' || item.status === 'routed' || item.action?.includes('approve')) {
    return 'chat-bubble positive';
  }
  if (item.status === 'defer' || item.status === 'no_trade') return 'chat-bubble muted-bubble';
  return 'chat-bubble';
}

function compactQuantity(value?: number | null) {
  if (!value) return null;
  return value.toLocaleString();
}

function latestSymbol(snapshot: SimulationSnapshot, feed: AgentActivityItem[]) {
  const activitySymbol = [...feed].reverse().find((item) => item.symbol)?.symbol;
  if (activitySymbol === 'PORTFOLIO') return 'portfolio slate';
  if (activitySymbol) return activitySymbol;
  if ((snapshot.candidate_slate?.length ?? 0) > 1) return 'portfolio slate';
  const decisionSymbol = snapshot.agent_decisions[snapshot.agent_decisions.length - 1]?.symbol;
  if (decisionSymbol === 'PORTFOLIO') return 'portfolio slate';
  return decisionSymbol ?? 'none';
}

function labelForTab(tab: DetailTab) {
  if (tab === 'inputs') return 'Inputs';
  if (tab === 'outputs') return 'Outputs';
  return tab[0].toUpperCase() + tab.slice(1);
}

function asText(value: unknown) {
  if (value === null || value === undefined) return '';
  return typeof value === 'string' ? value : String(value);
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function asList(value: unknown) {
  if (!Array.isArray(value)) return [];
  return value.map((item) => asText(item)).filter(Boolean);
}

function formatDetailValue(value: unknown) {
  if (Array.isArray(value)) return value.map((item) => asText(item)).filter(Boolean).join(', ');
  if (typeof value === 'boolean') return value ? 'yes' : 'no';
  if (typeof value === 'number') return value.toLocaleString();
  return asText(value);
}

function firstValue(...values: unknown[]) {
  return values.find((value) => {
    if (value === null || value === undefined) return false;
    if (Array.isArray(value)) return value.length > 0;
    return String(value).length > 0;
  });
}

function compactMetric(value: unknown, suffix = '') {
  if (value === null || value === undefined || value === '') return null;
  if (typeof value === 'number') return `${value.toLocaleString()}${suffix}`;
  return `${value}${suffix}`;
}

function parsedJsonString(value: unknown) {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  if (!trimmed || !['{', '['].includes(trimmed[0])) return null;
  try {
    return JSON.parse(trimmed) as unknown;
  } catch {
    return null;
  }
}

function referencesFor(snapshot: SimulationSnapshot, evidenceIds: string[]) {
  return evidenceIds.map((id) => {
    const event = snapshot.released_events.find((item) => item.id === id);
    if (!event) return { id, status: 'not_visible_or_unknown' };
    return {
      id: event.id,
      headline: event.headline,
      body: event.body,
      severity: event.severity,
      sentiment: event.sentiment_hint,
      affected_symbols: event.affected_symbols,
      timestamp: event.timestamp
    };
  });
}

function validatedOutput(detail: AgentActivityDetail) {
  return asRecord(detail.output.validated_json);
}

function namedOutput(detail: AgentActivityDetail, key: string) {
  return asRecord(detail.output[key]);
}

function overviewFacts(detail: AgentActivityDetail) {
  const validated = validatedOutput(detail);
  const proposal = namedOutput(detail, 'proposal');
  const decision = namedOutput(detail, 'committee_decision');
  const risk = namedOutput(detail, 'risk_review');
  const compliance = namedOutput(detail, 'compliance_review');
  const broker = namedOutput(detail, 'broker_decision');
  const fill = namedOutput(detail, 'fill');
  const agentState = namedOutput(detail, 'agent_state');
  const metrics = detail.metrics;
  const overview = detail.overview;
  const confidence = firstValue(validated?.confidence, decision?.confidence, agentState?.confidence);
  const latency = compactMetric(metrics.latency_ms, ' ms');
  const tokens = compactMetric(metrics.total_tokens);
  const facts = [
    ['Agent', overview.agent_id],
    ['Role', firstValue(overview.role, agentState?.role)],
    ['Ticker', firstValue(overview.symbol, validated?.symbol, proposal?.symbol, decision?.symbol, fill?.symbol)],
    ['Action', firstValue(overview.action, proposal?.side, decision?.final_decision, detail.output.action)],
    ['Quantity', firstValue(overview.quantity, proposal?.quantity, decision?.approved_quantity, fill?.quantity)],
    ['Status', firstValue(overview.status, detail.output.status, risk?.approved, compliance?.approved, broker?.accepted)],
    ['Confidence', confidence],
    ['Latency', latency],
    ['Tokens', tokens],
    ['Evidence', detail.references.length ? `${detail.references.length} item(s)` : null]
  ];
  return facts
    .map(([label, value]) => ({ label: String(label), value: formatDetailValue(value) }))
    .filter((item) => item.value);
}

function reasoningSections(detail: AgentActivityDetail) {
  const validated = validatedOutput(detail);
  const proposal = namedOutput(detail, 'proposal');
  const risk = namedOutput(detail, 'risk_review');
  const compliance = namedOutput(detail, 'compliance_review');
  const committee = namedOutput(detail, 'committee_decision');
  const broker = namedOutput(detail, 'broker_decision');
  const fill = namedOutput(detail, 'fill');
  const debate = namedOutput(detail, 'debate_message');
  const sections: { title: string; rows: { label: string; value: string }[] }[] = [];

  function add(title: string, rows: [string, unknown][]) {
    const filtered = rows
      .map(([label, value]) => ({ label, value: formatDetailValue(value) }))
      .filter((row) => row.value);
    if (filtered.length > 0) sections.push({ title, rows: filtered });
  }

  function addDecisionReasoning(source: Record<string, unknown> | null) {
    if (!source) return;
    add('Evidence summary', [
      ['Evidence used', source.evidence_summary],
      ['Evidence IDs', source.evidence_ids]
    ]);
    add('Key drivers', [
      ['Drivers', source.key_drivers],
      ['Assumptions', source.assumptions]
    ]);
    add('Counterpoints', [
      ['Counterpoints', source.counterpoints],
      ['Trade-offs', source.tradeoffs]
    ]);
    add('Decision rationale', [
      ['Rationale', firstValue(source.decision_rationale, source.rationale, source.claim)],
      ['Sizing rationale', source.sizing_rationale],
      ['Risk controls', source.risk_controls]
    ]);
  }

  if (validated?.direction || validated?.rationale || validated?.uncertainty) {
    add('Signal assessment', [
      ['Direction', validated.direction],
      ['Confidence', validated.confidence],
      ['Rationale', validated.rationale],
      ['Uncertainty', validated.uncertainty],
      ['Evidence IDs', validated.evidence_ids]
    ]);
    addDecisionReasoning(validated);
  }
  if (validated?.stance || validated?.claim || debate) {
    const source = debate ?? validated;
    if (source) {
      add('Debate position', [
        ['Stance', source.stance],
        ['Claim', firstValue(source.claim, source.message)],
        ['Confidence', source.confidence],
        ['Evidence IDs', source.evidence_ids]
      ]);
      addDecisionReasoning(source);
    }
  }
  if (proposal || validated?.side) {
    const source = proposal ?? validated;
    if (source) {
      add('Trade proposal', [
        ['Side', source.side],
        ['Quantity', source.quantity],
        ['Max notional', source.max_notional],
        ['Rationale', source.rationale],
        ['Confidence', source.confidence],
        ['Evidence IDs', source.evidence_ids]
      ]);
      addDecisionReasoning(source);
    }
  }
  if (risk) {
    add('Risk review', [
      ['Approved', risk.approved],
      ['Hard reject', risk.hard_reject],
      ['Suggested max quantity', risk.suggested_max_quantity],
      ['Risk score', risk.risk_score],
      ['Breached limits', risk.breached_limits],
      ['Reasons', risk.reasons]
    ]);
  }
  if (compliance) {
    add('Compliance review', [
      ['Approved', compliance.approved],
      ['Hard reject', compliance.hard_reject],
      ['Required changes', compliance.required_changes],
      ['Future leakage suspected', compliance.future_leakage_suspected],
      ['Reasons', compliance.reasons]
    ]);
  }
  if (committee) {
    add('Committee decision', [
      ['Final decision', committee.final_decision],
      ['Approved action', committee.approved_action],
      ['Approved quantity', committee.approved_quantity],
      ['Approved notional', committee.approved_notional],
      ['Order style', committee.required_order_style],
      ['Decision rationale', committee.primary_reason],
      ['Dissenting views', committee.dissenting_views],
      ['Constraints', [
        ...asList(committee.risk_constraints_applied),
        ...asList(committee.compliance_constraints_applied),
        ...asList(committee.execution_constraints_applied)
      ]]
    ]);
  }
  if (broker) {
    add('Broker route', [
      ['Accepted', broker.accepted],
      ['Reason', firstValue(broker.reason_text, broker.reason)],
      ['Approval token', broker.approval_token]
    ]);
  }
  if (fill) {
    add('Execution fill', [
      ['Symbol', fill.symbol],
      ['Side', fill.side],
      ['Quantity', fill.quantity],
      ['Price', fill.price],
      ['Order ID', fill.order_id]
    ]);
  }
  if (sections.length === 0) {
    add('Reasoning summary', [
      ['Summary', firstValue(detail.overview.reasoning_summary, detail.overview.message, detail.output.message)]
    ]);
  }
  return sections;
}

function activityDetail(
  snapshot: SimulationSnapshot,
  item: AgentActivityItem,
  input: Record<string, unknown>,
  output: Record<string, unknown>,
  overview: Record<string, unknown> = {}
): AgentActivityDetail {
  return {
    activity_id: item.id,
    overview: {
      title: item.title,
      message: item.message,
      kind: item.kind,
      agent_id: item.agent_id,
      cycle_id: item.cycle_id,
      symbol: item.symbol,
      action: item.action,
      quantity: item.quantity,
      status: item.status,
      timestamp: item.timestamp,
      reasoning_summary: item.message,
      source: 'reconstructed_from_snapshot',
      ...overview
    },
    input,
    output,
    references: referencesFor(snapshot, item.evidence_ids),
    validation: {
      source: 'reconstructed_from_snapshot',
      validation_summary: item.validation_summary
    },
    metrics: {}
  };
}

function kindForDecision(stage: string): AgentActivityItem['kind'] {
  if (stage === 'risk_review') return 'risk_review';
  if (stage === 'compliance_review') return 'compliance_review';
  if (stage === 'committee') return 'committee_decision';
  if (stage === 'broker') return 'broker_route';
  if (stage === 'fill') return 'fill';
  return 'proposal';
}

function titleForDecision(stage: string, action: string, symbol: string, status: string) {
  const label = stage.replace('_', ' ');
  if (stage === 'fill') return `Fill: ${action} ${symbol}`;
  if (stage === 'broker') return `Broker ${status.replace('_', ' ')} ${symbol}`;
  if (stage === 'committee') return `Committee ${status.replace('_', ' ')}`;
  return `${label}: ${action} ${symbol}`;
}

function recoveredTranscript(snapshot: SimulationSnapshot) {
  const source = 'Trace recovered from existing agent state because no live chat feed was recorded.';
  const feed: AgentActivityItem[] = [];
  const details: Record<string, AgentActivityDetail> = {};

  function push(
    item: AgentActivityItem,
    input: Record<string, unknown>,
    output: Record<string, unknown>,
    overview: Record<string, unknown> = {}
  ) {
    feed.push(item);
    details[item.id] = activityDetail(snapshot, item, input, output, overview);
  }

  snapshot.debate.forEach((message) => {
    const item: AgentActivityItem = {
      id: `recovered-debate-${message.id}`,
      timestamp: message.timestamp,
      cycle_id: message.id.split('-').slice(0, -1).join('-') || null,
      kind: 'debate',
      agent_id: message.agent_id,
      title: `${message.stance} debate argument`,
      message: message.message,
      status: message.stance,
      evidence_ids: message.evidence_ids,
      tool_call_ids: [],
      validation_summary: source
    };
    push(item, { debate_message: message }, { debate_message: message }, { stance: message.stance });
  });

  snapshot.agent_decisions.forEach((decision) => {
    const quantity =
      decision.filled_quantity || decision.approved_quantity || decision.requested_quantity || null;
    const item: AgentActivityItem = {
      id: `recovered-decision-${decision.id}`,
      timestamp: decision.timestamp,
      cycle_id: decision.cycle_id,
      kind: kindForDecision(decision.stage),
      agent_id: decision.agent_id,
      title: titleForDecision(decision.stage, decision.action, decision.symbol, decision.status),
      message: decision.rationale,
      symbol: decision.symbol,
      action: decision.action,
      quantity,
      status: decision.status,
      evidence_ids: decision.evidence_ids,
      tool_call_ids: decision.tool_call_ids,
      validation_summary: source
    };
    push(
      item,
      { decision_trace: decision },
      {
        action: decision.action,
        status: decision.status,
        requested_quantity: decision.requested_quantity,
        approved_quantity: decision.approved_quantity,
        filled_quantity: decision.filled_quantity,
        price: decision.price
      },
      { stage: decision.stage }
    );
  });

  snapshot.skill_calls.forEach((call) => {
    if (feed.some((item) => item.tool_call_ids.includes(call.id))) return;
    const item: AgentActivityItem = {
      id: `recovered-tool-${call.id}`,
      timestamp: snapshot.current_time,
      cycle_id: call.cycle_id ?? null,
      kind: 'tool_call',
      agent_id: call.agent_id,
      title: `Tool call: ${call.skill_name}`,
      message: call.output_summary,
      status: call.status,
      evidence_ids: [],
      tool_call_ids: [call.id],
      validation_summary: source
    };
    push(item, { input_summary: call.input_summary }, { output_summary: call.output_summary }, { ...call });
  });

  if (feed.length === 0) {
    snapshot.agent_states.forEach((agent) => {
      const item: AgentActivityItem = {
        id: `recovered-agent-${agent.agent_id}`,
        timestamp: snapshot.current_time,
        cycle_id: snapshot.active_cycle_id ?? null,
        kind: 'agent_completed',
        agent_id: agent.agent_id,
        title: `${agent.agent_id} state recovered`,
        message: agent.last_action,
        symbol: agent.target_symbol,
        action: agent.decision,
        quantity: agent.quantity,
        status: agent.status,
        evidence_ids: agent.evidence_ids ?? [],
        tool_call_ids: [],
        validation_summary: source
      };
      push(item, { agent_state: agent }, { agent_state: agent }, { role: agent.role, confidence: agent.confidence });
    });
  }

  return { feed, details };
}

function JsonBlock({ title, value }: { title: string; value: unknown }) {
  const rendered = JSON.stringify(value ?? {}, null, 2);
  async function copy() {
    if (!navigator.clipboard) return;
    await navigator.clipboard.writeText(rendered);
  }

  return (
    <div className="json-block">
      <div className="json-block-head">
        <strong>{title}</strong>
        <button className="btn" onClick={copy} type="button">
          Copy
        </button>
      </div>
      <pre>{rendered}</pre>
    </div>
  );
}

function TextBlock({ title, value }: { title: string; value: string }) {
  async function copy() {
    if (!navigator.clipboard) return;
    await navigator.clipboard.writeText(value);
  }

  return (
    <div className="json-block">
      <div className="json-block-head">
        <strong>{title}</strong>
        <button className="btn" onClick={copy} type="button">
          Copy
        </button>
      </div>
      <pre>{value}</pre>
    </div>
  );
}

function OutputBlocks({ output }: { output: Record<string, unknown> }) {
  const raw = output.raw_structured_output;
  const parsedRaw = parsedJsonString(raw);
  const validated = output.validated_json;
  const remaining = { ...output };
  delete remaining.message;
  delete remaining.raw_structured_output;
  delete remaining.validated_json;

  return (
    <>
      {typeof output.message === 'string' && output.message && (
        <section className="reasoning-card">
          <strong>Message</strong>
          <p>{output.message}</p>
        </section>
      )}
      {parsedRaw ? (
        <>
          <JsonBlock title="Raw structured output (parsed)" value={parsedRaw} />
          <TextBlock title="Raw structured output (original)" value={String(raw)} />
        </>
      ) : raw !== undefined ? (
        <JsonBlock title="Raw structured output" value={raw} />
      ) : null}
      {validated !== undefined && <JsonBlock title="Validated JSON" value={validated} />}
      {Object.keys(remaining).length > 0 && <JsonBlock title="Other outputs" value={remaining} />}
    </>
  );
}

function DetailPanel({
  detail,
  error,
  loading,
  tab,
  setTab
}: {
  detail: AgentActivityDetail | null;
  error: string | null;
  loading: boolean;
  tab: DetailTab;
  setTab: Dispatch<SetStateAction<DetailTab>>;
}) {
  if (loading) return <aside className="agent-detail-panel muted">Loading detail...</aside>;
  if (error) return <aside className="agent-detail-panel muted">{error}</aside>;
  if (!detail) {
    return (
      <aside className="agent-detail-panel muted">
        Select a chat entry to inspect model-visible inputs, outputs, references, and validation.
      </aside>
    );
  }

  const reasoningSummary = asText(detail.overview.reasoning_summary);
  const facts = overviewFacts(detail);
  const sections = reasoningSections(detail);

  return (
    <aside className="agent-detail-panel">
      <div className="detail-panel-head">
        <div>
          <span className="muted">Selected activity</span>
          <strong>{asText(detail.overview.title) || detail.activity_id}</strong>
        </div>
      </div>
      <div className="segmented detail-tabs">
        {detailTabs.map((item) => (
          <button className={tab === item ? 'active' : ''} key={item} onClick={() => setTab(item)}>
            {labelForTab(item)}
          </button>
        ))}
      </div>

      {tab === 'overview' && (
        <div className="detail-stack">
          <div>
            <span className="muted">Reasoning summary</span>
            <p>{reasoningSummary || asText(detail.overview.message)}</p>
          </div>
          {facts.length > 0 && (
            <div className="detail-fact-grid">
              {facts.map((item) => (
                <div className="detail-fact" key={item.label}>
                  <span className="muted">{item.label}</span>
                  <strong>{item.value}</strong>
                </div>
              ))}
            </div>
          )}
          {sections.map((section) => (
            <section className="reasoning-card" key={section.title}>
              <strong>{section.title}</strong>
              <dl>
                {section.rows.map((row) => (
                  <div key={row.label}>
                    <dt>{row.label}</dt>
                    <dd>{row.value}</dd>
                  </div>
                ))}
              </dl>
            </section>
          ))}
          <JsonBlock title="Overview" value={detail.overview} />
          <JsonBlock title="Metrics" value={detail.metrics} />
        </div>
      )}
      {tab === 'inputs' && (
        <div className="detail-stack">
          <span className="muted">AI-visible input and tool/request inputs</span>
          <JsonBlock title="Inputs" value={detail.input} />
        </div>
      )}
      {tab === 'outputs' && (
        <div className="detail-stack">
          <span className="muted">Raw structured output and validated outputs</span>
          <OutputBlocks output={detail.output} />
        </div>
      )}
      {tab === 'references' && (
        <div className="detail-stack">
          <span className="muted">Evidence and released market references</span>
          <JsonBlock title="References" value={detail.references} />
        </div>
      )}
      {tab === 'validation' && (
        <div className="detail-stack">
          <span className="muted">Schema repair, permission, and validation status</span>
          <JsonBlock title="Validation" value={detail.validation} />
        </div>
      )}
    </aside>
  );
}

export function AgentSocietyLive({ snapshot, emptyReason, activityDetailLoader }: Props) {
  const [open, setOpen] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [followLatest, setFollowLatest] = useState(true);
  const [detailCache, setDetailCache] = useState<Record<string, AgentActivityDetail>>({});
  const [loadingActivityId, setLoadingActivityId] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<{ activityId: string; message: string } | null>(null);
  const [detailTab, setDetailTab] = useState<DetailTab>('overview');
  const serverFeed = snapshot.agent_activity_feed ?? [];
  const recovered = useMemo(() => recoveredTranscript(snapshot), [snapshot]);
  const feed = serverFeed.length > 0 ? serverFeed : recovered.feed;
  const recoveredMode = serverFeed.length === 0 && feed.length > 0;
  const latest = feed[feed.length - 1];
  const latestId = latest?.id ?? null;
  const selectedExists = useMemo(
    () => Boolean(selectedId && feed.some((item) => item.id === selectedId)),
    [feed, selectedId]
  );
  const recoveredDetail = selectedId ? recovered.details[selectedId] : undefined;
  const cachedDetail = selectedId ? detailCache[selectedId] ?? null : null;
  const selectedError = detailError?.activityId === selectedId ? detailError.message : null;
  const detailLoading = Boolean(
    selectedId && !cachedDetail && !selectedError && (!loadingActivityId || loadingActivityId === selectedId)
  );
  const running = snapshot.agent_cycle_status === 'running';
  const symbol = latestSymbol(snapshot, feed);
  const expected = Math.max(1, snapshot.expected_llm_calls ?? 0);
  const progress = Math.min(1, (snapshot.completed_llm_calls ?? 0) / expected);
  const emptyMessage = running
    ? `${snapshot.active_agent ?? 'Agent'} is calling the AI runtime.`
    : snapshot.status === 'running'
      ? 'Waiting for next agent cycle.'
      : emptyReason ?? 'Press Start to begin the agent transcript.';

  useEffect(() => {
    if (!open) return;
    if (!latestId) {
      if (selectedId) setSelectedId(null);
      return;
    }
    if (!selectedId || !selectedExists || followLatest) {
      if (selectedId !== latestId) setSelectedId(latestId);
    }
  }, [followLatest, latestId, open, selectedExists, selectedId]);

  useEffect(() => {
    if (!open || !selectedId) return;
    if (cachedDetail) return;
    if (recoveredDetail) {
      setDetailCache((current) =>
        current[selectedId] ? current : { ...current, [selectedId]: recoveredDetail }
      );
      setDetailError(null);
      return;
    }
    let cancelled = false;
    setLoadingActivityId(selectedId);
    setDetailError(null);
    const loadDetail =
      activityDetailLoader?.load ??
      ((activityId: string) => getAgentActivityDetail(snapshot.simulation_id, activityId));
    Promise.resolve(loadDetail(selectedId) as Promise<AgentActivityDetail>)
      .then((loaded: AgentActivityDetail) => {
        if (!cancelled) {
          setDetailCache((current) => ({ ...current, [selectedId]: loaded }));
        }
      })
      .catch((error: Error) => {
        if (!cancelled) {
          setDetailError({ activityId: selectedId, message: error.message });
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingActivityId((current) => (current === selectedId ? null : current));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [activityDetailLoader, cachedDetail, open, recoveredDetail, selectedId, snapshot.simulation_id]);

  function selectActivity(item: AgentActivityItem) {
    setSelectedId(item.id);
    setFollowLatest(false);
  }

  function openChat() {
    setOpen(true);
    if (!selectedId && latestId) setSelectedId(latestId);
  }

  function toggleFollowLatest() {
    const next = !followLatest;
    setFollowLatest(next);
    if (next && latestId) setSelectedId(latestId);
  }

  return (
    <>
      <section className={`panel span-12 agent-live compact-side-panel ${running ? 'agent-live-running' : ''}`}>
        <h2>Agent Society Live</h2>
        <div className="panel-body live-preview compact-agent-live-body">
          <div className="live-preview-main">
            <div className="toolbar">
              <span className={running ? 'badge green' : 'badge'}>
                <MessageSquareText size={14} />
                {snapshot.agent_cycle_status ?? 'idle'}
              </span>
              <span className="badge mono">{symbol}</span>
              {recoveredMode && <span className="badge warning">trace recovered</span>}
            </div>
            <strong>{latest?.title ?? 'Waiting for agent activity'}</strong>
            <p className="muted">{latest?.message ?? emptyMessage}</p>
            <div className="live-progress">
              <progress max={1} value={progress} aria-label="Agent society progress" />
              <span className="mono">
                {snapshot.completed_llm_calls ?? 0}/{snapshot.expected_llm_calls ?? 0}
              </span>
            </div>
          </div>
          <button className="btn primary" onClick={openChat}>
            <Maximize2 size={15} />
            Open chat
          </button>
        </div>
      </section>

      {open && (
        <div className="modal-backdrop" onClick={() => setOpen(false)}>
          <section
            aria-label="Agent Society Live chat"
            aria-modal="true"
            className="panel agent-chat-modal"
            onClick={(event) => event.stopPropagation()}
            role="dialog"
          >
            <h2>
              <span>Agent Society Chat</span>
              <button className="btn icon-btn" onClick={() => setOpen(false)} aria-label="Close agent chat">
                <X size={16} />
              </button>
            </h2>
            <div className="panel-body">
              <div className="chat-summary">
                <span className="badge">{snapshot.active_agent ?? 'no active agent'}</span>
                <span className="badge mono">{symbol}</span>
                <button className={followLatest ? 'btn active' : 'btn'} onClick={toggleFollowLatest} type="button">
                  Follow latest
                </button>
              </div>

              <div className="agent-chat-content">
                <div className="agent-chat-log">
                {feed.length === 0 ? (
                  <p className="muted">{emptyMessage}</p>
                ) : (
                  feed.map((item) => (
                    <article
                      className={`${activityClass(item)} chat-bubble-clickable ${selectedId === item.id ? 'selected' : ''}`}
                      key={item.id}
                      onClick={() => selectActivity(item)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') selectActivity(item);
                      }}
                      role="button"
                      tabIndex={0}
                    >
                      <div className="chat-bubble-head">
                        <span className="badge">
                          {activityIcon(item.kind, item.status)}
                          {item.agent_id ?? 'system'}
                        </span>
                        {item.symbol && <span className="badge mono">{item.symbol}</span>}
                        {item.status && <span className="badge">{item.status.replace('_', ' ')}</span>}
                      </div>
                      <strong>{item.title}</strong>
                      <p>{item.message}</p>
                      <div className="chat-bubble-meta">
                        {item.action && <span className="badge">{item.action.replace('_', ' ')}</span>}
                        {compactQuantity(item.quantity) && <span className="badge">{compactQuantity(item.quantity)} shares</span>}
                        {item.repair_status && (
                          <span className={item.repair_status === 'fallback' ? 'badge warning' : 'badge green'}>
                            {item.repair_status}
                          </span>
                        )}
                        {item.evidence_ids.length > 0 && (
                          <span className="badge">Evidence used: {item.evidence_ids.join(', ')}</span>
                        )}
                        {item.tool_call_ids.length > 0 && (
                          <span className="badge">Tools: {item.tool_call_ids.length}</span>
                        )}
                      </div>
                    </article>
                  ))
                )}
                </div>
                <DetailPanel
                  detail={cachedDetail}
                  error={selectedError}
                  loading={detailLoading}
                  tab={detailTab}
                  setTab={setDetailTab}
                />
              </div>
            </div>
          </section>
        </div>
      )}
    </>
  );
}
