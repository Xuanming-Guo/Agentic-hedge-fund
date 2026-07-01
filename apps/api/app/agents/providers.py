from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Protocol, TypeVar

from pydantic import BaseModel

from app.schemas.agent_outputs import (
    ComplianceReview,
    DebateArgument,
    ExecutionPlan,
    PortfolioAllocationProposal,
    RiskReview,
    SignalReport,
    TradeProposal,
)

T = TypeVar("T", bound=BaseModel)


@dataclass(slots=True)
class LLMResult:
    content_json: dict
    raw_text: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: int
    repair_status: str | None = None
    validation_summary: str | None = None


class LLMProvider(Protocol):
    async def complete_json(
        self,
        *,
        agent_name: str,
        system_prompt: str,
        user_prompt: str,
        response_schema: type[T],
        temperature: float,
        max_tokens: int | None,
        metadata: dict,
    ) -> LLMResult: ...


class MockLLMProvider:
    provider_name = "mock"

    async def complete_json(
        self,
        *,
        agent_name: str,
        system_prompt: str,
        user_prompt: str,
        response_schema: type[T],
        temperature: float,
        max_tokens: int | None,
        metadata: dict,
    ) -> LLMResult:
        started = time.perf_counter()
        payload = self._payload(agent_name, response_schema, metadata)
        validated = response_schema.model_validate(payload)
        raw_text = validated.model_dump_json()
        latency_ms = int((time.perf_counter() - started) * 1000)
        return LLMResult(
            content_json=json.loads(raw_text),
            raw_text=raw_text,
            provider=self.provider_name,
            model="mock-deterministic",
            prompt_tokens=max(1, len(system_prompt) // 4 + len(user_prompt) // 4),
            completion_tokens=max(1, len(raw_text) // 4),
            total_tokens=max(2, (len(system_prompt) + len(user_prompt) + len(raw_text)) // 4),
            latency_ms=latency_ms,
        )

    def _payload(self, agent_name: str, response_schema: type[BaseModel], metadata: dict) -> dict:
        event_ids = metadata.get("event_ids", [])
        symbol = metadata.get("symbol", "ALPH")
        sentiment = metadata.get("symbol_sentiment", "neutral")
        side = "sell" if sentiment == "bearish" else "buy"
        direction = (
            "bullish"
            if sentiment == "bullish"
            else "bearish"
            if sentiment == "bearish"
            else "neutral"
        )
        cycle_id = metadata.get("cycle_id", "cycle-0")
        proposal_id = metadata.get("proposal_id", f"{cycle_id}-{symbol}-proposal")
        if response_schema is SignalReport:
            evidence_summary = (
                f"Uses released evidence IDs {', '.join(event_ids[-2:])}."
                if event_ids
                else "No released evidence IDs are available yet; signal stays monitor/neutral."
            )
            return {
                "agent_id": agent_name,
                "symbol": symbol,
                "direction": direction,
                "confidence": 0.76 if direction != "neutral" else 0.51,
                "evidence_ids": event_ids[-2:],
                "rationale": f"{agent_name} sees point-in-time evidence for {direction} {symbol}.",
                "uncertainty": "Macro tape and execution costs remain the key uncertainty.",
                "evidence_summary": evidence_summary,
                "key_drivers": [
                    f"Point-in-time symbol sentiment is {sentiment}.",
                    f"Current cycle is scoped to {symbol}.",
                ],
                "counterpoints": [
                    "No position should be taken without released evidence and later risk checks."
                    if not event_ids
                    else (
                        "Liquidity, slippage, and committee constraints may still resize the trade."
                    )
                ],
                "decision_rationale": (
                    f"Keep {symbol} neutral until a released catalyst appears."
                    if direction == "neutral"
                    else f"Use the released catalyst to support a {direction} specialist signal."
                ),
            }
        if response_schema is DebateArgument:
            stance = "bear" if "Bear" in agent_name else "bull"
            claim = (
                f"{symbol} has a tradable released catalyst, but size should be constrained."
                if stance == "bull"
                else f"{symbol} still faces adverse tape, liquidity, or compliance risk."
            )
            return {
                "agent_id": agent_name,
                "stance": stance,
                "symbol": symbol,
                "claim": claim,
                "evidence_ids": event_ids[-2:],
                "confidence": 0.72,
                "evidence_summary": (
                    f"Debate references released evidence IDs {', '.join(event_ids[-2:])}."
                    if event_ids
                    else "Debate is monitoring-only because no released evidence is visible."
                ),
                "counterpoints": [
                    "Bull case still needs risk-sized execution."
                    if stance == "bull"
                    else "Bear case may be outweighed by strong symbol-specific evidence."
                ],
                "decision_rationale": claim,
            }
        if response_schema is TradeProposal:
            hold = not event_ids
            proposal_side = "hold" if hold else side
            quantity = 0 if hold else 1600 if side == "buy" else 500
            return {
                "proposal_id": proposal_id,
                "symbol": symbol,
                "side": proposal_side,
                "quantity": quantity,
                "max_notional": 0 if hold else 200000,
                "rationale": (
                    "Monitoring only because no released evidence IDs are visible."
                    if hold
                    else f"Proposal is based only on released {symbol} events "
                    "and current orderbook context."
                ),
                "evidence_ids": event_ids[-2:],
                "confidence": 0.74,
                "evidence_summary": (
                    f"Proposal uses released evidence IDs {', '.join(event_ids[-2:])}."
                    if event_ids
                    else "No released evidence is available, so the proposal is no-trade."
                ),
                "key_drivers": [
                    f"Specialist consensus is anchored to {symbol}.",
                    f"Symbol sentiment is {sentiment}.",
                ],
                "counterpoints": [
                    (
                        "Committee may defer if disagreement, liquidity, or compliance "
                        "constraints dominate."
                    )
                ],
                "sizing_rationale": (
                    "Quantity is zero until point-in-time evidence is released."
                    if hold
                    else (
                        f"{quantity} shares keeps notional below the simulated max-notional "
                        "guardrail."
                    )
                ),
                "risk_controls": [
                    "Use only released evidence",
                    "Route through pre-trade risk",
                    "Route through compliance",
                    "Allow committee resize/defer",
                ],
            }
        if response_schema is PortfolioAllocationProposal:
            candidate_slate = [
                item for item in metadata.get("candidate_slate", []) if isinstance(item, dict)
            ]
            basket_evidence_ids = [
                str(item) for item in metadata.get("event_ids", []) if isinstance(item, str)
            ]
            selected: list[dict] = []
            rejected: list[dict] = []
            role_counts = {"primary": 0, "hedge": 0, "relative_value": 0}
            for candidate in candidate_slate:
                side_hint = str(candidate.get("side_hint") or "hold")
                score = float(candidate.get("score") or 0)
                candidate_events = [
                    str(item) for item in candidate.get("event_ids", []) if isinstance(item, str)
                ]
                allocation_role = str(
                    candidate.get("allocation_role")
                    or (
                        "primary"
                        if candidate_events and side_hint in {"buy", "sell"}
                        else "watchlist"
                    )
                )
                if allocation_role not in {"primary", "hedge", "relative_value", "watchlist"}:
                    allocation_role = "watchlist"
                hold_reason = candidate.get("hold_reason")
                has_basket_evidence = bool(candidate_events or basket_evidence_ids)
                eligible = False
                if side_hint in {"buy", "sell"}:
                    if allocation_role == "primary":
                        eligible = bool(candidate_events)
                    elif allocation_role == "hedge":
                        eligible = has_basket_evidence and score >= 0.16
                    elif allocation_role == "relative_value":
                        eligible = has_basket_evidence and score >= 0.30
                    else:
                        eligible = has_basket_evidence and score >= 0.72
                if eligible and allocation_role in role_counts:
                    eligible = role_counts[allocation_role] < (
                        1 if allocation_role in {"hedge", "relative_value"} else 3
                    )
                evidence_ids = candidate_events[-3:]
                if not evidence_ids and allocation_role in {"hedge", "relative_value"}:
                    evidence_ids = basket_evidence_ids[-3:]
                summary = {
                    "symbol": str(candidate.get("symbol") or symbol),
                    "score": max(0.0, min(1.0, score)),
                    "side": side_hint if side_hint in {"buy", "sell"} else "hold",
                    "allocation_role": allocation_role,
                    "hold_reason": str(hold_reason) if hold_reason else None,
                    "reason": str(
                        candidate.get("reason")
                        or "Candidate was ranked by deterministic portfolio features."
                    ),
                    "evidence_ids": evidence_ids,
                    "relationship_notes": [
                        str(item) for item in candidate.get("relation_notes", [])[:4]
                    ],
                }
                if eligible and len(selected) < 3:
                    selected.append(summary)
                    if allocation_role in role_counts:
                        role_counts[allocation_role] += 1
                else:
                    if not summary["hold_reason"]:
                        summary["hold_reason"] = (
                            "no direct event"
                            if not candidate_events and allocation_role == "watchlist"
                            else "score too weak"
                        )
                    rejected.append(summary)
            proposals = []
            for index, candidate in enumerate(selected, start=1):
                candidate_symbol = candidate["symbol"]
                candidate_side = candidate["side"]
                score = float(candidate["score"])
                quantity = max(50, min(5000, int(350 + score * 1800)))
                if candidate_side == "sell":
                    quantity = max(50, min(1800, int(quantity * 0.55)))
                proposals.append(
                    {
                        "proposal_id": f"{cycle_id}-{candidate_symbol}-proposal-{index}",
                        "symbol": candidate_symbol,
                        "side": candidate_side,
                        "allocation_role": candidate["allocation_role"],
                        "hold_reason": None,
                        "quantity": quantity,
                        "max_notional": 225000,
                        "rationale": (
                            f"{candidate_symbol} is a {candidate['allocation_role']} leg in "
                            f"the portfolio slate with score {score:.2f}; route through "
                            "risk and committee sizing."
                        ),
                        "evidence_ids": candidate["evidence_ids"],
                        "confidence": max(0.52, min(0.88, score)),
                        "evidence_summary": (
                            "Proposal uses released evidence IDs: "
                            + ", ".join(candidate["evidence_ids"])
                            + "."
                            if candidate["evidence_ids"]
                            else (
                                "No released evidence IDs; proposal depends on a strong "
                                "deterministic cross-ticker score."
                            )
                        ),
                        "key_drivers": [
                            candidate["reason"],
                            "Ranked against the full active ticker slate.",
                        ],
                        "counterpoints": [
                            (
                                "Basket sizing remains subject to risk, compliance, "
                                "and committee gates."
                            )
                        ],
                        "sizing_rationale": (
                            f"{quantity} shares reflects a score-weighted simulated basket size."
                        ),
                        "risk_controls": [
                            "Max three names per cycle",
                            "Check released evidence or portfolio hedge support",
                            "Run independent risk/compliance/committee review",
                        ],
                    }
                )
            if not proposals:
                proposals = [
                    {
                        "proposal_id": proposal_id,
                        "symbol": symbol,
                        "side": "hold",
                        "quantity": 0,
                        "max_notional": 0,
                        "rationale": "No candidate cleared the evidence and score gates.",
                        "evidence_ids": event_ids[-2:],
                        "confidence": 0.5,
                        "evidence_summary": (
                            "Monitoring references released evidence IDs "
                            f"{', '.join(event_ids[-2:])}."
                            if event_ids
                            else "No released evidence IDs are available."
                        ),
                        "key_drivers": ["Candidate slate did not produce a tradable basket."],
                        "counterpoints": ["Opportunity cost of waiting."],
                        "sizing_rationale": "No routeable quantity.",
                        "risk_controls": ["Maintain cash until a stronger edge appears."],
                    }
                ]
            ranked_candidates = selected + rejected
            return {
                "allocation_id": f"{cycle_id}-allocation",
                "proposals": proposals[:3],
                "ranked_candidates": ranked_candidates[: len(candidate_slate) or 5],
                "rejected_candidates": rejected[:5],
                "allocation_rationale": (
                    "Portfolio manager ranked all active tickers and selected the strongest "
                    "risk-gated basket candidates."
                ),
                "exposure_notes": [
                    "Diversify across sectors unless a catalyst dominates.",
                    "Avoid adding to already large existing positions.",
                    "Every proposed child order remains simulated only.",
                ],
            }
        if response_schema is RiskReview:
            return {
                "proposal_id": proposal_id,
                "approved": True,
                "hard_reject": False,
                "suggested_max_quantity": metadata.get("suggested_max_quantity", 800),
                "risk_score": 0.44,
                "breached_limits": ["ELEVATED_VOLATILITY"],
                "reasons": ["Mock risk review resized the trade under elevated volatility."],
            }
        if response_schema is ComplianceReview:
            return {
                "proposal_id": proposal_id,
                "approved": bool(event_ids),
                "hard_reject": False,
                "required_changes": [] if event_ids else ["Attach evidence IDs."],
                "reasons": [
                    "Mock compliance found valid released evidence."
                    if event_ids
                    else "Missing released evidence."
                ],
                "future_leakage_suspected": False,
            }
        if response_schema is ExecutionPlan:
            return {
                "proposal_id": proposal_id,
                "symbol": symbol,
                "side": side,
                "child_orders": [
                    {
                        "order_type": "limit",
                        "quantity": metadata.get("quantity", 500),
                        "time_in_force": "DAY",
                        "style": "passive",
                    }
                ],
                "rationale": "Slice through passive limit orders to reduce slippage.",
                "broker_approval_token": metadata.get("approval_token"),
            }
        return {}
