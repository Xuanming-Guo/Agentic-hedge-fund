from __future__ import annotations


class AgenticHedgeFundError(Exception):
    """Base exception for the simulation platform."""


class ValidationError(AgenticHedgeFundError):
    pass


class RiskLimitError(AgenticHedgeFundError):
    pass


class ComplianceError(AgenticHedgeFundError):
    pass


class BrokerRejectionError(AgenticHedgeFundError):
    pass


class ExchangeError(AgenticHedgeFundError):
    pass


class SimulationStateError(AgenticHedgeFundError):
    pass


class LLMProviderError(AgenticHedgeFundError):
    pass
