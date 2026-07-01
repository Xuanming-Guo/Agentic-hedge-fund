from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from app.schemas.agent_outputs import ComplianceReview, RiskReview
from app.schemas.market import PortfolioState

ReasonCode = Literal[
    "MARKET_CLOSED",
    "UNKNOWN_SYMBOL",
    "INVALID_QUANTITY",
    "INVALID_PRICE",
    "INSUFFICIENT_CASH",
    "INSUFFICIENT_BUYING_POWER",
    "MARGIN_LIMIT",
    "SHORT_LOCATE_UNAVAILABLE",
    "RISK_LIMIT_BREACH",
    "COMPLIANCE_REJECTED",
    "SELF_TRADE_PREVENTION",
    "RESTRICTED_SYMBOL",
    "MALFORMED_ORDER",
    "DUPLICATE_CLIENT_ORDER_ID",
]


@dataclass(slots=True)
class BrokerDecision:
    accepted: bool
    reason_codes: list[ReasonCode]
    reason_text: str
    approval_token: str | None = None


class BrokerService:
    def __init__(self, symbols: set[str]) -> None:
        self.symbols = symbols
        self.client_order_ids: set[str] = set()

    def validate_order_intent(
        self,
        *,
        simulation_id: str,
        client_order_id: str,
        symbol: str,
        side: Literal["buy", "sell"],
        quantity: int,
        price: Decimal,
        portfolio: PortfolioState,
        risk: RiskReview,
        compliance: ComplianceReview,
        market_open: bool,
    ) -> BrokerDecision:
        reasons: list[ReasonCode] = []
        text: list[str] = []
        if not market_open:
            reasons.append("MARKET_CLOSED")
            text.append("Market is closed.")
        if symbol not in self.symbols:
            reasons.append("UNKNOWN_SYMBOL")
            text.append("Unknown symbol.")
        if quantity <= 0:
            reasons.append("INVALID_QUANTITY")
            text.append("Quantity must be positive.")
        if price <= 0:
            reasons.append("INVALID_PRICE")
            text.append("Price must be positive.")
        if client_order_id in self.client_order_ids:
            reasons.append("DUPLICATE_CLIENT_ORDER_ID")
            text.append("Duplicate client order ID.")
        if side == "buy" and Decimal(str(portfolio.cash)) < price * Decimal(quantity):
            reasons.append("INSUFFICIENT_CASH")
            text.append("Insufficient cash for order notional.")
        if side == "sell" and symbol == "CYGN":
            reasons.append("SHORT_LOCATE_UNAVAILABLE")
            text.append("Short locate unavailable for CYGN in this scenario.")
        if risk.hard_reject or not risk.approved:
            reasons.append("RISK_LIMIT_BREACH")
            text.append("; ".join(risk.reasons))
        if compliance.hard_reject or not compliance.approved:
            reasons.append("COMPLIANCE_REJECTED")
            text.append("; ".join(compliance.reasons))

        accepted = not reasons
        if accepted:
            self.client_order_ids.add(client_order_id)
        return BrokerDecision(
            accepted=accepted,
            reason_codes=reasons,
            reason_text=" ".join(text) if text else "Broker accepted order for simulated routing.",
            approval_token=f"{simulation_id}:{client_order_id}:approved" if accepted else None,
        )
