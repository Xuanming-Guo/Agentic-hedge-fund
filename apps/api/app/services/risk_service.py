from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.schemas.agent_outputs import RiskReview, TradeProposal
from app.schemas.market import PortfolioState


@dataclass(slots=True)
class RiskLimits:
    max_gross_exposure_pct: Decimal = Decimal("1.20")
    max_net_exposure_pct: Decimal = Decimal("1.00")
    max_single_name_pct: Decimal = Decimal("0.20")
    max_order_notional_pct: Decimal = Decimal("0.20")
    elevated_volatility_threshold: Decimal = Decimal("0.035")


class RiskService:
    def __init__(self, limits: RiskLimits | None = None) -> None:
        self.limits = limits or RiskLimits()

    def pre_trade_check(
        self,
        proposal: TradeProposal,
        portfolio: PortfolioState,
        latest_price: Decimal,
        volatility: Decimal,
    ) -> RiskReview:
        equity = Decimal(str(max(portfolio.equity, 1)))
        requested_notional = Decimal(proposal.quantity) * latest_price
        max_order_notional = equity * self.limits.max_order_notional_pct
        suggested = proposal.quantity
        reasons: list[str] = []
        breached: list[str] = []
        hard_reject = False

        if requested_notional > max_order_notional:
            suggested = int(max_order_notional / latest_price)
            breached.append("MAX_ORDER_NOTIONAL")
            reasons.append("Requested notional exceeds per-order risk budget.")

        if volatility > self.limits.elevated_volatility_threshold:
            suggested = min(suggested, max(1, proposal.quantity // 2))
            breached.append("ELEVATED_VOLATILITY")
            reasons.append("Volatility is elevated, so the trade is resized.")

        projected_single = requested_notional / equity
        if projected_single > self.limits.max_single_name_pct:
            suggested = min(
                suggested, int((equity * self.limits.max_single_name_pct) / latest_price)
            )
            breached.append("MAX_SINGLE_NAME_EXPOSURE")
            reasons.append("Single-name exposure would exceed the configured limit.")

        if proposal.quantity <= 0:
            hard_reject = True
            breached.append("INVALID_QUANTITY")
            reasons.append("Quantity must be positive.")

        approved = not hard_reject and suggested > 0
        risk_score = min(
            1.0, float(projected_single * Decimal("3")) + float(volatility * Decimal("8"))
        )
        return RiskReview(
            proposal_id=proposal.proposal_id,
            approved=approved,
            hard_reject=hard_reject,
            suggested_max_quantity=max(0, suggested),
            risk_score=round(risk_score, 3),
            breached_limits=breached,
            reasons=reasons or ["Trade is within deterministic risk limits."],
        )
