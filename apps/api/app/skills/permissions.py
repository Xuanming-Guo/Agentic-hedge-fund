from __future__ import annotations

from enum import StrEnum


class PermissionLevel(StrEnum):
    READ_MARKET = "READ_MARKET"
    READ_PORTFOLIO = "READ_PORTFOLIO"
    READ_RISK = "READ_RISK"
    READ_ORDERBOOK = "READ_ORDERBOOK"
    RUN_CALCULATION = "RUN_CALCULATION"
    REQUEST_RISK_CHECK = "REQUEST_RISK_CHECK"
    REQUEST_COMPLIANCE_CHECK = "REQUEST_COMPLIANCE_CHECK"
    PROPOSE_TRADE = "PROPOSE_TRADE"
    SUBMIT_ORDER_PLAN = "SUBMIT_ORDER_PLAN"
    ROUTE_APPROVED_ORDER = "ROUTE_APPROVED_ORDER"
    RUN_BENCHMARK = "RUN_BENCHMARK"
    WRITE_AUDIT_LOG = "WRITE_AUDIT_LOG"


AGENT_PERMISSIONS: dict[str, set[PermissionLevel]] = {
    "MacroAnalystAgent": {PermissionLevel.READ_MARKET, PermissionLevel.RUN_CALCULATION},
    "FundamentalAnalystAgent": {PermissionLevel.READ_MARKET, PermissionLevel.RUN_CALCULATION},
    "TechnicalAnalystAgent": {
        PermissionLevel.READ_MARKET,
        PermissionLevel.READ_ORDERBOOK,
        PermissionLevel.RUN_CALCULATION,
    },
    "SentimentNewsAnalystAgent": {PermissionLevel.READ_MARKET},
    "BullResearcherAgent": {PermissionLevel.READ_MARKET, PermissionLevel.READ_ORDERBOOK},
    "BearResearcherAgent": {PermissionLevel.READ_MARKET, PermissionLevel.READ_ORDERBOOK},
    "ResearchManagerAgent": {PermissionLevel.READ_MARKET, PermissionLevel.READ_PORTFOLIO},
    "PortfolioManagerAgent": {
        PermissionLevel.READ_MARKET,
        PermissionLevel.READ_PORTFOLIO,
        PermissionLevel.PROPOSE_TRADE,
    },
    "RiskManagerAgent": {
        PermissionLevel.READ_PORTFOLIO,
        PermissionLevel.READ_RISK,
        PermissionLevel.REQUEST_RISK_CHECK,
    },
    "ComplianceOfficerAgent": {
        PermissionLevel.READ_MARKET,
        PermissionLevel.REQUEST_COMPLIANCE_CHECK,
        PermissionLevel.WRITE_AUDIT_LOG,
    },
    "InvestmentCommitteeChairAgent": {
        PermissionLevel.READ_MARKET,
        PermissionLevel.READ_PORTFOLIO,
        PermissionLevel.READ_RISK,
    },
    "ExecutionTraderAgent": {
        PermissionLevel.READ_ORDERBOOK,
        PermissionLevel.SUBMIT_ORDER_PLAN,
        PermissionLevel.ROUTE_APPROVED_ORDER,
    },
    "DemoNarratorAgent": {PermissionLevel.READ_MARKET, PermissionLevel.RUN_BENCHMARK},
}
