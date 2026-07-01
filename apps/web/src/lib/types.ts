export type Scenario = {
  id: string;
  display_date: string;
  title: string;
  description: string;
  seed: number;
  status: string;
};

export type Instrument = {
  symbol: string;
  display_name: string;
  sector: string;
  tick_size: number;
  lot_size: number;
  starting_price: number;
};

export type MarketDataMetadata = {
  mode: string;
  provider: string;
  feed: string;
  is_delayed: boolean;
  quote_source: string;
  depth_source: string;
  requested_tickers: string[];
  active_tickers: string[];
  replay_date: string | null;
  warning: string | null;
};

export type NewsEvent = {
  id: string;
  timestamp: string;
  headline: string;
  body: string;
  affected_symbols: string[];
  severity: number;
  sentiment_hint: string;
  event_type: string;
};

export type MarketBar = {
  symbol: string;
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type OrderBookSnapshot = {
  symbol: string;
  bids: {
    price: number;
    quantity: number;
    order_count?: number | null;
    participants?: { owner_type: string; order_count: number; quantity: number }[];
  }[];
  asks: {
    price: number;
    quantity: number;
    order_count?: number | null;
    participants?: { owner_type: string; order_count: number; quantity: number }[];
  }[];
  mid: number;
  spread: number;
  imbalance: number;
  last_trade: number | null;
  market_data_mode?: string;
  feed?: string;
  is_delayed?: boolean;
  quote_source?: string;
  depth_source?: string;
};

export type PortfolioState = {
  cash: number;
  equity: number;
  realized_pnl: number;
  unrealized_pnl: number;
  gross_exposure: number;
  net_exposure: number;
  sector_exposure: Record<string, number>;
  positions: {
    symbol: string;
    quantity: number;
    average_price: number;
    market_price: number;
    market_value: number;
    unrealized_pnl: number;
  }[];
};

export type PortfolioHistoryPoint = {
  timestamp: string;
  equity: number;
  cash: number;
  total_pnl: number;
  realized_pnl: number;
  unrealized_pnl: number;
  gross_exposure: number;
  net_exposure: number;
};

export type CandidateSlateItem = {
  symbol: string;
  rank: number;
  score: number;
  side_hint: 'buy' | 'sell' | 'hold';
  allocation_role: 'primary' | 'hedge' | 'relative_value' | 'watchlist';
  hold_reason?: string | null;
  reason: string;
  event_ids: string[];
  event_count: number;
  latest_price: number;
  recent_return_pct: number;
  volatility_pct: number;
  volume_ratio: number;
  spread_bps: number;
  orderbook_imbalance: number;
  sector: string;
  current_position: number;
  relation_notes: string[];
};

export type AgentState = {
  agent_id: string;
  role: string;
  status: string;
  last_action: string;
  confidence: number;
  model: string;
  target_symbol?: string | null;
  decision?: string | null;
  quantity?: number | null;
  evidence_ids?: string[];
};

export type DebateMessage = {
  id: string;
  timestamp: string;
  agent_id: string;
  stance: string;
  message: string;
  evidence_ids: string[];
  symbol?: string | null;
};

export type SkillCallView = {
  id: string;
  simulation_id?: string;
  cycle_id?: string | null;
  agent_id: string | null;
  skill_name: string;
  mode: string;
  input_summary: string;
  output_summary: string;
  status: string;
  permission_decision: string;
  latency_ms: number;
  side_effecting: boolean;
};

export type AgentDecisionTrace = {
  id: string;
  cycle_id: string;
  timestamp: string;
  agent_id: string;
  stage: string;
  symbol: string;
  action: string;
  requested_quantity: number;
  approved_quantity: number;
  filled_quantity: number;
  price: number | null;
  status: string;
  rationale: string;
  evidence_ids: string[];
  tool_call_ids: string[];
};

export type AgentActivityItem = {
  id: string;
  timestamp: string;
  cycle_id: string | null;
  kind:
    | 'cycle_start'
    | 'agent_started'
    | 'agent_completed'
    | 'tool_call'
    | 'debate'
    | 'proposal'
    | 'risk_review'
    | 'compliance_review'
    | 'committee_decision'
    | 'broker_route'
    | 'fill'
    | 'error';
  agent_id: string | null;
  title: string;
  message: string;
  symbol?: string | null;
  action?: string | null;
  quantity?: number | null;
  status?: string | null;
  provider?: string | null;
  model?: string | null;
  repair_status?: 'normalized' | 'repaired' | 'fallback' | null;
  validation_summary?: string | null;
  evidence_ids: string[];
  tool_call_ids: string[];
};

export type AgentActivityDetail = {
  activity_id: string;
  overview: Record<string, unknown>;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  references: Record<string, unknown>[];
  validation: Record<string, unknown>;
  metrics: Record<string, unknown>;
};

export type CommitteeDecision = {
  id: string;
  cycle_id: string;
  symbol: string;
  final_decision: string;
  approved_action: string;
  approved_quantity: number;
  approved_notional: number;
  required_order_style: string;
  primary_reason: string;
  dissenting_views: string[];
  risk_constraints_applied: string[];
  compliance_constraints_applied: string[];
  execution_constraints_applied: string[];
  confidence: number;
  evidence_ids: string[];
};

export type ConsensusSnapshot = {
  symbol: string;
  consensus_direction: string;
  consensus_strength: number;
  disagreement_score: number;
  uncertainty_score: number;
  movers: string[];
};

export type ConflictRecord = {
  id: string;
  conflict_type: string;
  issue: string;
  agents_involved: string[];
  proposed_solution: string;
  final_decision: string;
  winning_constraint: string;
};

export type BenchmarkMetric = {
  mode: string;
  total_return_pct: number;
  max_drawdown_pct: number;
  sharpe_like: number;
  risk_violations: number;
  compliance_rejections: number;
  directional_accuracy: number;
  decision_quality: number;
  token_usage: number;
};

export type BenchmarkReport = {
  benchmark_run_id: string;
  score: number;
  metrics: BenchmarkMetric[];
  explanation: string;
};

export type SimulationSnapshot = {
  simulation_id: string;
  scenario: Scenario;
  instruments: Instrument[];
  market_data: MarketDataMetadata;
  status: string;
  current_time: string;
  speed: number;
  released_events: NewsEvent[];
  latest_bars: MarketBar[];
  history_bars: MarketBar[];
  orderbooks: OrderBookSnapshot[];
  trade_tape: {
    id: string;
    timestamp: string;
    symbol: string;
    side: string;
    price: number;
    quantity: number;
    owner_type: string;
  }[];
  portfolio: PortfolioState;
  portfolio_history?: PortfolioHistoryPoint[];
  candidate_slate?: CandidateSlateItem[];
  agent_states: AgentState[];
  debate: DebateMessage[];
  conflicts: ConflictRecord[];
  agent_decisions: AgentDecisionTrace[];
  committee_decisions: CommitteeDecision[];
  consensus: ConsensusSnapshot[];
  skill_calls: SkillCallView[];
  agent_activity_feed?: AgentActivityItem[];
  benchmark: BenchmarkReport | null;
  agent_cycle_status?: 'idle' | 'running' | 'complete' | 'error';
  active_cycle_id?: string | null;
  active_agent?: string | null;
  active_provider?: string | null;
  configured_provider?: string | null;
  completed_llm_calls?: number;
  expected_llm_calls?: number;
  last_llm_error?: string | null;
  last_llm_provider?: string | null;
  last_completed_provider?: string | null;
  last_fallback_provider?: string | null;
  last_fallback_agent?: string | null;
  last_fallback_reason?: string | null;
  last_llm_model?: string | null;
  last_llm_calls?: number;
  last_llm_tokens?: number;
};

export type RecordingManifest = {
  recording_id: string;
  simulation_id: string;
  name: string;
  scenario_id: string;
  scenario_title: string;
  status: 'running' | 'complete' | 'incomplete' | 'failed';
  duration_minutes: number;
  simulated_start: string;
  simulated_end: string | null;
  created_at: string;
  updated_at: string;
  market_data_mode?: string;
  tickers?: string[];
  frame_count: number;
  event_count: number;
  last_frame_index: number;
  can_continue: boolean;
  summary: string;
};

export type SimulationRecordingFrame = {
  index: number;
  timestamp: string;
  elapsed_sim_minutes: number;
  snapshot: SimulationSnapshot;
};

export type SimulationRecordingKeyframe = {
  frame_index: number;
  event_index: number;
  reason: string;
  frame: SimulationRecordingFrame;
};

export type ReplayBenchmarkPoint = {
  frame_index: number;
  event_index: number;
  reason: string;
  timestamp: string;
  benchmark: BenchmarkReport;
};

export type ReplayBenchmarkRun = {
  recording_id: string;
  scope: 'keyframes';
  items: ReplayBenchmarkPoint[];
  summary: BenchmarkReport | null;
};

export type SimulationEstimate = {
  duration_minutes: number;
  expected_agent_cycles: number;
  expected_llm_calls: number;
  estimated_real_seconds: number;
  warning: string;
};

export type RecordedSimulationResponse = {
  recording: RecordingManifest;
  snapshot: SimulationSnapshot;
};

export type QwenProof = {
  provider_configured: boolean;
  json_mode_enabled: boolean;
  function_calling_enabled: boolean;
  mcp_enabled: boolean;
  last_agent_run_id: string | null;
  last_fallback_agent: string | null;
  last_fallback_reason: string | null;
  last_llm_calls: number;
  last_llm_tokens: number;
  last_tool_call_id: string | null;
  tool_gateway_configured: boolean;
  mcp_configured: boolean;
};
