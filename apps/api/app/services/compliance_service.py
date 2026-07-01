from __future__ import annotations

from app.schemas.agent_outputs import ComplianceReview, TradeProposal


class ComplianceService:
    restricted_symbols = {"NONE"}
    future_terms = {"future return", "tomorrow close", "hidden label", "realized movement"}

    def pre_trade_check(
        self,
        proposal: TradeProposal,
        current_event_ids: set[str],
        event_symbol_map: dict[str, set[str]] | None = None,
    ) -> ComplianceReview:
        reasons: list[str] = []
        required_changes: list[str] = []
        future_leakage = any(term in proposal.rationale.lower() for term in self.future_terms)
        if proposal.symbol in self.restricted_symbols:
            reasons.append("Symbol is restricted.")
        missing_evidence = [
            evidence_id
            for evidence_id in proposal.evidence_ids
            if evidence_id not in current_event_ids
        ]
        if not proposal.evidence_ids or missing_evidence:
            required_changes.append("Attach point-in-time evidence IDs before trading.")
            reasons.append("Trade lacks valid released evidence.")
        irrelevant_evidence = [
            evidence_id
            for evidence_id in proposal.evidence_ids
            if event_symbol_map is not None
            and proposal.symbol not in event_symbol_map.get(evidence_id, set())
        ]
        basket_supported = proposal.allocation_role in {"hedge", "relative_value"} and bool(
            proposal.evidence_ids
        )
        if irrelevant_evidence and not basket_supported:
            required_changes.append("Use evidence that directly affects the proposed symbol.")
            reasons.append(
                "Evidence IDs are released but do not apply to "
                f"{proposal.symbol}: {', '.join(irrelevant_evidence)}."
            )
        elif irrelevant_evidence:
            reasons.append(
                "Basket leg uses released catalyst evidence as portfolio-construction context."
            )
        if future_leakage:
            reasons.append("Rationale appears to reference future or hidden data.")
        hard_reject = proposal.symbol in self.restricted_symbols or future_leakage
        approved = (
            not hard_reject
            and not missing_evidence
            and (not irrelevant_evidence or basket_supported)
            and bool(proposal.evidence_ids)
        )
        return ComplianceReview(
            proposal_id=proposal.proposal_id,
            approved=approved,
            hard_reject=hard_reject,
            required_changes=required_changes,
            reasons=reasons or ["Compliance approved based on released evidence."],
            future_leakage_suspected=future_leakage,
        )
