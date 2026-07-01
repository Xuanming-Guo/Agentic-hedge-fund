from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Instrument(BaseModel):
    symbol: str
    display_name: str
    sector: str
    tick_size: float
    lot_size: int
    starting_price: float


class Scenario(BaseModel):
    id: str
    display_date: str
    title: str
    description: str
    seed: int
    status: str = "active"


class MarketBar(BaseModel):
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class NewsEvent(BaseModel):
    id: str
    scenario_id: str
    timestamp: datetime
    headline: str
    body: str
    affected_symbols: list[str]
    affected_sectors: list[str]
    severity: int = Field(ge=1, le=5)
    sentiment_hint: Literal["bullish", "bearish", "mixed", "neutral"]
    event_type: str
    public: bool = True


class OrderBookParticipant(BaseModel):
    owner_type: str
    order_count: int
    quantity: int


class OrderBookLevel(BaseModel):
    price: float
    quantity: int
    order_count: int | None = None
    participants: list[OrderBookParticipant] = Field(default_factory=list)


class OrderBookSnapshot(BaseModel):
    symbol: str
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]
    mid: float
    spread: float
    imbalance: float
    last_trade: float | None = None
    market_data_mode: str = "synthetic"
    feed: str = "synthetic"
    is_delayed: bool = False
    quote_source: str = "synthetic"
    depth_source: str = "synthetic_limit_order_book"


class MarketDataMetadata(BaseModel):
    mode: str = "synthetic"
    provider: str = "synthetic"
    feed: str = "synthetic"
    is_delayed: bool = False
    quote_source: str = "synthetic"
    depth_source: str = "synthetic_limit_order_book"
    requested_tickers: list[str] = Field(default_factory=list)
    active_tickers: list[str] = Field(default_factory=list)
    replay_date: str | None = None
    warning: str | None = None


class TradeTapeItem(BaseModel):
    id: str
    timestamp: datetime
    symbol: str
    side: Literal["buy", "sell"]
    price: float
    quantity: int
    owner_type: str


class Position(BaseModel):
    symbol: str
    quantity: int
    average_price: float
    market_price: float
    market_value: float
    unrealized_pnl: float


class PortfolioState(BaseModel):
    cash: float
    equity: float
    realized_pnl: float
    unrealized_pnl: float
    gross_exposure: float
    net_exposure: float
    sector_exposure: dict[str, float]
    positions: list[Position]


class PortfolioHistoryPoint(BaseModel):
    timestamp: datetime
    equity: float
    cash: float
    total_pnl: float
    realized_pnl: float
    unrealized_pnl: float
    gross_exposure: float
    net_exposure: float


class CandidateSlateItem(BaseModel):
    symbol: str
    rank: int
    score: float = Field(ge=0.0, le=1.0)
    side_hint: Literal["buy", "sell", "hold"]
    allocation_role: Literal["primary", "hedge", "relative_value", "watchlist"] = (
        "watchlist"
    )
    hold_reason: str | None = None
    reason: str
    event_ids: list[str] = Field(default_factory=list)
    event_count: int = 0
    latest_price: float
    recent_return_pct: float
    volatility_pct: float
    volume_ratio: float
    spread_bps: float
    orderbook_imbalance: float
    sector: str
    current_position: int = 0
    relation_notes: list[str] = Field(default_factory=list)


class AgentState(BaseModel):
    agent_id: str
    role: str
    status: str
    last_action: str
    confidence: float
    model: str
    target_symbol: str | None = None
    decision: str | None = None
    quantity: int | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class DebateMessage(BaseModel):
    id: str
    timestamp: datetime
    agent_id: str
    stance: str
    message: str
    evidence_ids: list[str]
    symbol: str | None = None


class ConflictRecord(BaseModel):
    id: str
    conflict_type: str
    issue: str
    agents_involved: list[str]
    proposed_solution: str
    final_decision: str
    winning_constraint: str


class AgentDecisionTrace(BaseModel):
    id: str
    cycle_id: str
    timestamp: datetime
    agent_id: str
    stage: str
    symbol: str
    action: str
    requested_quantity: int = 0
    approved_quantity: int = 0
    filled_quantity: int = 0
    price: float | None = None
    status: str
    rationale: str
    evidence_ids: list[str] = Field(default_factory=list)
    tool_call_ids: list[str] = Field(default_factory=list)


class SkillCallView(BaseModel):
    id: str
    simulation_id: str
    cycle_id: str | None
    agent_id: str | None
    skill_name: str
    mode: str
    input_summary: str
    output_summary: str
    status: str
    permission_decision: str
    latency_ms: int
    side_effecting: bool


class AgentActivityItem(BaseModel):
    id: str
    timestamp: datetime
    cycle_id: str | None = None
    kind: Literal[
        "cycle_start",
        "agent_started",
        "agent_completed",
        "tool_call",
        "debate",
        "proposal",
        "risk_review",
        "compliance_review",
        "committee_decision",
        "broker_route",
        "fill",
        "error",
    ]
    agent_id: str | None = None
    title: str
    message: str
    symbol: str | None = None
    action: str | None = None
    quantity: int | None = None
    status: str | None = None
    provider: str | None = None
    model: str | None = None
    repair_status: Literal["normalized", "repaired", "fallback"] | None = None
    validation_summary: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    tool_call_ids: list[str] = Field(default_factory=list)


class AgentActivityDetail(BaseModel):
    activity_id: str
    overview: dict[str, Any] = Field(default_factory=dict)
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    references: list[dict[str, Any]] = Field(default_factory=list)
    validation: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)


class CommitteeDecisionView(BaseModel):
    id: str
    cycle_id: str
    symbol: str
    final_decision: str
    approved_action: str
    approved_quantity: int
    approved_notional: float
    required_order_style: str
    primary_reason: str
    dissenting_views: list[str]
    risk_constraints_applied: list[str]
    compliance_constraints_applied: list[str]
    execution_constraints_applied: list[str]
    confidence: float
    evidence_ids: list[str]


class ConsensusSnapshot(BaseModel):
    symbol: str
    consensus_direction: Literal["bullish", "bearish", "neutral"]
    consensus_strength: float
    disagreement_score: float
    uncertainty_score: float
    movers: list[str]


class BenchmarkMetrics(BaseModel):
    mode: str
    total_return_pct: float
    max_drawdown_pct: float
    sharpe_like: float
    risk_violations: int
    compliance_rejections: int
    directional_accuracy: float
    decision_quality: float
    token_usage: int


class AgentSocietyAdvantageReport(BaseModel):
    benchmark_run_id: str
    score: float
    metrics: list[BenchmarkMetrics]
    explanation: str


class SimulationSnapshot(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    simulation_id: str
    scenario: Scenario
    instruments: list[Instrument] = Field(default_factory=list)
    market_data: MarketDataMetadata = Field(default_factory=MarketDataMetadata)
    status: Literal["created", "running", "paused", "closed"]
    current_time: datetime
    speed: float
    released_events: list[NewsEvent]
    latest_bars: list[MarketBar]
    history_bars: list[MarketBar]
    orderbooks: list[OrderBookSnapshot]
    trade_tape: list[TradeTapeItem]
    portfolio: PortfolioState
    portfolio_history: list[PortfolioHistoryPoint] = Field(default_factory=list)
    candidate_slate: list[CandidateSlateItem] = Field(default_factory=list)
    agent_states: list[AgentState]
    debate: list[DebateMessage]
    conflicts: list[ConflictRecord]
    agent_decisions: list[AgentDecisionTrace]
    committee_decisions: list[CommitteeDecisionView]
    consensus: list[ConsensusSnapshot]
    skill_calls: list[SkillCallView]
    agent_activity_feed: list[AgentActivityItem] = Field(default_factory=list)
    benchmark: AgentSocietyAdvantageReport | None = None
    agent_cycle_status: Literal["idle", "running", "complete", "error"] = "idle"
    active_cycle_id: str | None = None
    active_agent: str | None = None
    active_provider: str | None = None
    configured_provider: str | None = None
    completed_llm_calls: int = 0
    expected_llm_calls: int = 0
    last_llm_error: str | None = None
    last_llm_provider: str | None = None
    last_completed_provider: str | None = None
    last_fallback_provider: str | None = None
    last_fallback_agent: str | None = None
    last_fallback_reason: str | None = None
    last_llm_model: str | None = None
    last_llm_calls: int = 0
    last_llm_tokens: int = 0
