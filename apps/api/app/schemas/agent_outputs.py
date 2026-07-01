from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SignalReport(BaseModel):
    agent_id: str
    symbol: str
    direction: Literal["bullish", "bearish", "neutral"]
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str]
    rationale: str
    uncertainty: str
    evidence_summary: str | None = None
    key_drivers: list[str] = Field(default_factory=list)
    counterpoints: list[str] = Field(default_factory=list)
    decision_rationale: str | None = None


class DebateArgument(BaseModel):
    agent_id: str
    stance: Literal["bull", "bear", "neutral"]
    symbol: str
    claim: str
    evidence_ids: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_summary: str | None = None
    counterpoints: list[str] = Field(default_factory=list)
    decision_rationale: str | None = None


class TradeProposal(BaseModel):
    proposal_id: str
    symbol: str
    side: Literal["buy", "sell", "hold"]
    allocation_role: Literal["primary", "hedge", "relative_value", "watchlist"] = (
        "primary"
    )
    hold_reason: str | None = None
    quantity: int
    max_notional: float
    rationale: str
    evidence_ids: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_summary: str | None = None
    key_drivers: list[str] = Field(default_factory=list)
    counterpoints: list[str] = Field(default_factory=list)
    sizing_rationale: str | None = None
    risk_controls: list[str] = Field(default_factory=list)


class CandidateAllocation(BaseModel):
    symbol: str
    score: float = Field(ge=0.0, le=1.0)
    side: Literal["buy", "sell", "hold"]
    allocation_role: Literal["primary", "hedge", "relative_value", "watchlist"] = (
        "watchlist"
    )
    hold_reason: str | None = None
    reason: str
    evidence_ids: list[str] = Field(default_factory=list)
    relationship_notes: list[str] = Field(default_factory=list)


class PortfolioAllocationProposal(BaseModel):
    allocation_id: str
    proposals: list[TradeProposal] = Field(default_factory=list)
    ranked_candidates: list[CandidateAllocation] = Field(default_factory=list)
    rejected_candidates: list[CandidateAllocation] = Field(default_factory=list)
    allocation_rationale: str
    exposure_notes: list[str] = Field(default_factory=list)


class RiskReview(BaseModel):
    proposal_id: str
    approved: bool
    hard_reject: bool
    suggested_max_quantity: int
    risk_score: float
    breached_limits: list[str]
    reasons: list[str]


class ComplianceReview(BaseModel):
    proposal_id: str
    approved: bool
    hard_reject: bool
    required_changes: list[str]
    reasons: list[str]
    future_leakage_suspected: bool


class CommitteeDecision(BaseModel):
    cycle_id: str
    proposal_id: str
    symbol: str
    final_decision: Literal["approve", "approve_resized", "reject", "defer", "no_trade"]
    approved_action: Literal["buy", "sell", "hold"]
    approved_quantity: int
    approved_notional: float
    required_order_style: str
    primary_reason: str
    dissenting_views: list[str]
    risk_constraints_applied: list[str]
    compliance_constraints_applied: list[str]
    execution_constraints_applied: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str]


class ExecutionPlan(BaseModel):
    proposal_id: str
    symbol: str
    side: Literal["buy", "sell"]
    child_orders: list[dict]
    rationale: str
    broker_approval_token: str | None = None
