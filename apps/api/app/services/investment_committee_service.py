from __future__ import annotations

from app.schemas.agent_outputs import CommitteeDecision, ComplianceReview, RiskReview, TradeProposal


class InvestmentCommitteeService:
    def decide(
        self,
        *,
        cycle_id: str,
        proposal: TradeProposal,
        risk: RiskReview,
        compliance: ComplianceReview,
        disagreement_score: float,
        impact_bps: float,
    ) -> CommitteeDecision:
        if compliance.hard_reject or not compliance.approved:
            final = "reject"
            quantity = 0
            reason = "Compliance constraints block the proposal."
        elif risk.hard_reject or not risk.approved:
            final = "reject"
            quantity = 0
            reason = "Risk constraints block the proposal."
        elif disagreement_score > 0.7 and proposal.confidence < 0.65:
            final = "no_trade"
            quantity = 0
            reason = "Disagreement remains high and expected edge is weak."
        elif impact_bps > 45:
            final = "defer"
            quantity = 0
            reason = "Execution impact is too high for immediate routing."
        elif risk.suggested_max_quantity < proposal.quantity:
            final = "approve_resized"
            quantity = risk.suggested_max_quantity
            reason = "Committee accepts deterministic risk resize."
        else:
            final = "approve"
            quantity = proposal.quantity
            reason = "Evidence, risk, compliance, and execution checks support action."

        return CommitteeDecision(
            cycle_id=cycle_id,
            proposal_id=proposal.proposal_id,
            symbol=proposal.symbol,
            final_decision=final,
            approved_action=proposal.side if quantity > 0 else "hold",
            approved_quantity=quantity,
            approved_notional=proposal.max_notional if quantity > 0 else 0.0,
            required_order_style="marketable IOC limit"
            if final in {"approve", "approve_resized"}
            else "none",
            primary_reason=reason,
            dissenting_views=["BearResearcher: macro tape is hostile and spread widened."]
            if proposal.symbol == "ALPH"
            else [],
            risk_constraints_applied=risk.breached_limits,
            compliance_constraints_applied=compliance.required_changes,
            execution_constraints_applied=["IOC-liquidity-check"] if impact_bps > 25 else [],
            confidence=min(proposal.confidence, 0.86),
            evidence_ids=proposal.evidence_ids,
        )
