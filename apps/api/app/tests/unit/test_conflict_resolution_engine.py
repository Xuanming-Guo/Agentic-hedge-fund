from __future__ import annotations

from app.schemas.agent_outputs import ComplianceReview, RiskReview, TradeProposal
from app.services.investment_committee_service import InvestmentCommitteeService


def proposal() -> TradeProposal:
    return TradeProposal(
        proposal_id="p1",
        symbol="ALPH",
        side="buy",
        quantity=1000,
        max_notional=100000,
        rationale="released evidence only",
        evidence_ids=["event-1"],
        confidence=0.7,
    )


def test_committee_resizes_when_risk_requires_resize() -> None:
    risk = RiskReview(
        proposal_id="p1",
        approved=True,
        hard_reject=False,
        suggested_max_quantity=500,
        risk_score=0.5,
        breached_limits=["ELEVATED_VOLATILITY"],
        reasons=["resize"],
    )
    compliance = ComplianceReview(
        proposal_id="p1",
        approved=True,
        hard_reject=False,
        required_changes=[],
        reasons=["ok"],
        future_leakage_suspected=False,
    )
    decision = InvestmentCommitteeService().decide(
        cycle_id="c1",
        proposal=proposal(),
        risk=risk,
        compliance=compliance,
        disagreement_score=0.2,
        impact_bps=10,
    )
    assert decision.final_decision == "approve_resized"
    assert decision.approved_quantity == 500
