from __future__ import annotations

import pytest

from app.agents.providers import MockLLMProvider
from app.agents.structured_output import normalize_payload
from app.schemas.agent_outputs import (
    DebateArgument,
    PortfolioAllocationProposal,
    SignalReport,
    TradeProposal,
)


def test_signal_report_normalizes_hold_and_numeric_uncertainty() -> None:
    payload, changed, summary = normalize_payload(
        {
            "symbol": "ALPH",
            "direction": "HOLD",
            "confidence": 0.55,
            "rationale": "No setup yet.",
            "uncertainty": 1.0,
        },
        SignalReport,
        agent_name="TechnicalAnalystAgent",
        metadata={"symbol": "ALPH", "event_ids": []},
    )

    validated = SignalReport.model_validate(payload)

    assert changed is True
    assert summary
    assert validated.direction == "neutral"
    assert validated.uncertainty == "Uncertainty score: 1.00."
    assert validated.agent_id == "TechnicalAnalystAgent"
    assert validated.evidence_ids == []
    assert validated.evidence_summary == (
        "No released evidence IDs were available in the point-in-time context."
    )
    assert validated.key_drivers == ["No setup yet."]
    assert validated.counterpoints == ["Uncertainty score: 1.00."]
    assert validated.decision_rationale == "No setup yet."


def test_debate_argument_normalizes_bullish_and_missing_fields() -> None:
    payload, changed, _ = normalize_payload(
        {"message": "Released evidence supports upside risk.", "stance": "bullish"},
        DebateArgument,
        agent_name="BullResearcherAgent",
        metadata={"symbol": "ALPH", "event_ids": ["event-1"]},
    )

    validated = DebateArgument.model_validate(payload)

    assert changed is True
    assert validated.agent_id == "BullResearcherAgent"
    assert validated.stance == "bull"
    assert validated.symbol == "ALPH"
    assert validated.claim == "Released evidence supports upside risk."
    assert validated.evidence_ids == ["event-1"]
    assert validated.evidence_summary == "Uses released evidence IDs: event-1."
    assert validated.counterpoints == ["Opposing agents may weigh the same evidence differently."]
    assert validated.decision_rationale == "Released evidence supports upside risk."


def test_trade_proposal_hold_becomes_monitor_outcome() -> None:
    payload, changed, _ = normalize_payload(
        {
            "proposal_id": "hold-001",
            "action": "hold",
            "rationale": "No released catalyst.",
            "confidence": 0.3,
        },
        TradeProposal,
        agent_name="PortfolioManagerAgent",
        metadata={"symbol": "ALPH", "event_ids": [], "cycle_id": "cycle-1"},
    )

    validated = TradeProposal.model_validate(payload)

    assert changed is True
    assert validated.side == "hold"
    assert validated.quantity == 0
    assert validated.max_notional == 0.0
    assert validated.evidence_ids == []
    assert validated.evidence_summary == (
        "No released evidence IDs were available in the point-in-time context."
    )
    assert validated.sizing_rationale == (
        "Quantity is zero because the agent is monitoring until released evidence appears."
    )
    assert "Require released evidence IDs" in validated.risk_controls


def test_trade_proposal_preserves_provider_reasoning_fields() -> None:
    payload, _, _ = normalize_payload(
        {
            "proposal_id": "buy-001",
            "side": "buy",
            "quantity": 250,
            "max_notional": 50_000,
            "rationale": "Buy small after released demand evidence.",
            "evidence_summary": "Uses S2 and S4 released catalysts.",
            "key_drivers": ["Demand beat", "Tight spread"],
            "counterpoints": ["Macro tape is hostile"],
            "sizing_rationale": "Small pilot size under liquidity and volatility constraints.",
            "risk_controls": ["Stop if compliance rejects", "Committee can resize"],
            "confidence": 0.7,
        },
        TradeProposal,
        agent_name="PortfolioManagerAgent",
        metadata={"symbol": "ALPH", "event_ids": ["S2", "S4"], "cycle_id": "cycle-1"},
    )

    validated = TradeProposal.model_validate(payload)

    assert validated.evidence_summary == "Uses S2 and S4 released catalysts."
    assert validated.key_drivers == ["Demand beat", "Tight spread"]
    assert validated.counterpoints == ["Macro tape is hostile"]
    assert validated.sizing_rationale == (
        "Small pilot size under liquidity and volatility constraints."
    )
    assert validated.risk_controls == ["Stop if compliance rejects", "Committee can resize"]


@pytest.mark.asyncio
async def test_mock_provider_returns_demo_friendly_reasoning_fields() -> None:
    provider = MockLLMProvider()

    result = await provider.complete_json(
        agent_name="PortfolioManagerAgent",
        system_prompt="Return strict JSON.",
        user_prompt="Use only visible context.",
        response_schema=TradeProposal,
        temperature=0,
        max_tokens=900,
        metadata={
            "symbol": "ALPH",
            "symbol_sentiment": "bullish",
            "event_ids": ["S4"],
            "cycle_id": "cycle-1",
        },
    )

    validated = TradeProposal.model_validate(result.content_json)

    assert validated.evidence_summary
    assert validated.key_drivers
    assert validated.counterpoints
    assert validated.sizing_rationale
    assert "Route through pre-trade risk" in validated.risk_controls


def test_portfolio_allocation_normalizes_candidates_and_proposals() -> None:
    payload, changed, _ = normalize_payload(
        {
            "rationale": "Route the strongest basket names.",
            "trades": [
                {
                    "symbol": "ALPH",
                    "action": "buy",
                    "quantity": 250,
                    "confidence": 0.78,
                },
                {
                    "symbol": "ECHO",
                    "action": "sell",
                    "quantity": 120,
                    "confidence": 0.72,
                },
            ],
        },
        PortfolioAllocationProposal,
        agent_name="PortfolioManagerAgent",
        metadata={
            "symbol": "ALPH",
            "cycle_id": "cycle-1",
            "event_ids": ["S4", "S5"],
            "candidate_slate": [
                {
                    "symbol": "ALPH",
                    "score": 0.82,
                    "side_hint": "buy",
                    "allocation_role": "primary",
                    "reason": "Top catalyst score.",
                    "event_ids": ["S4"],
                    "relation_notes": ["software peer leader"],
                },
                {
                    "symbol": "ECHO",
                    "score": 0.75,
                    "side_hint": "sell",
                    "allocation_role": "relative_value",
                    "reason": "Rate-sensitive weakness.",
                    "event_ids": ["S5"],
                },
            ],
        },
    )

    validated = PortfolioAllocationProposal.model_validate(payload)

    assert changed is True
    assert validated.allocation_id == "cycle-1-allocation"
    assert [proposal.symbol for proposal in validated.proposals] == ["ALPH", "ECHO"]
    assert validated.proposals[0].evidence_ids == ["S4"]
    assert validated.proposals[0].allocation_role == "primary"
    assert validated.ranked_candidates[1].allocation_role == "relative_value"
    assert validated.ranked_candidates[0].symbol == "ALPH"
    assert validated.allocation_rationale == "Route the strongest basket names."


@pytest.mark.asyncio
async def test_mock_provider_returns_portfolio_allocation_from_slate() -> None:
    provider = MockLLMProvider()

    result = await provider.complete_json(
        agent_name="PortfolioManagerAgent",
        system_prompt="Return strict JSON.",
        user_prompt="Rank the slate.",
        response_schema=PortfolioAllocationProposal,
        temperature=0,
        max_tokens=900,
        metadata={
            "symbol": "ALPH",
            "symbol_sentiment": "bullish",
            "event_ids": ["S4", "S5"],
            "cycle_id": "cycle-1",
            "candidate_slate": [
                {
                    "symbol": "ALPH",
                    "score": 0.85,
                    "side_hint": "buy",
                    "allocation_role": "primary",
                    "reason": "Strong catalyst.",
                    "event_ids": ["S4"],
                    "relation_notes": [],
                },
                {
                    "symbol": "ECHO",
                    "score": 0.79,
                    "side_hint": "sell",
                    "allocation_role": "relative_value",
                    "reason": "Sector weakness.",
                    "event_ids": ["S5"],
                    "relation_notes": [],
                },
                {
                    "symbol": "BRAV",
                    "score": 0.2,
                    "side_hint": "hold",
                    "allocation_role": "watchlist",
                    "hold_reason": "score too weak",
                    "reason": "Low score.",
                    "event_ids": [],
                    "relation_notes": [],
                },
            ],
        },
    )

    validated = PortfolioAllocationProposal.model_validate(result.content_json)

    assert len(validated.proposals) == 2
    assert [proposal.symbol for proposal in validated.proposals] == ["ALPH", "ECHO"]
    assert [proposal.allocation_role for proposal in validated.proposals] == [
        "primary",
        "relative_value",
    ]
    assert validated.rejected_candidates[0].symbol == "BRAV"
    assert validated.rejected_candidates[0].hold_reason == "score too weak"
