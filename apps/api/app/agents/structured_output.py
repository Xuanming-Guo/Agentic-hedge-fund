from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

from app.schemas.agent_outputs import (
    DebateArgument,
    PortfolioAllocationProposal,
    SignalReport,
    TradeProposal,
)

NEUTRAL_TERMS = {"hold", "flat", "no_trade", "no trade", "monitor", "wait", "neutral"}
BULL_TERMS = {"bull", "bullish", "buy", "long", "positive", "upside", "pro"}
BEAR_TERMS = {"bear", "bearish", "sell", "short", "negative", "downside", "contra"}
ALLOCATION_ROLES = {"primary", "hedge", "relative_value", "watchlist"}


def _string(value: Any, default: str) -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value
    return str(value)


def _number(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, parsed))


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _list(value: Any, default: list[str]) -> list[str]:
    if value is None:
        return default
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str) and value:
        return [value]
    return default


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = _string(value, "").strip()
    return text or None


def _summary_from_evidence(evidence_ids: list[str]) -> str:
    if not evidence_ids:
        return "No released evidence IDs were available in the point-in-time context."
    return f"Uses released evidence IDs: {', '.join(evidence_ids)}."


def _term(value: Any) -> str:
    return _string(value, "").strip().lower().replace("-", "_")


def _metadata_events(metadata: dict[str, Any]) -> list[str]:
    return [str(item) for item in metadata.get("event_ids", [])]


def _metadata_candidates(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = metadata.get("candidate_slate", [])
    if not isinstance(candidates, list):
        return []
    return [dict(item) for item in candidates if isinstance(item, dict)]


def _candidate_by_symbol(metadata: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(candidate.get("symbol")): candidate
        for candidate in _metadata_candidates(metadata)
        if candidate.get("symbol")
    }


def _candidate_summary(candidate: dict[str, Any], *, default_symbol: str) -> dict[str, Any]:
    symbol = _string(candidate.get("symbol"), default_symbol)
    side = _side(
        candidate.get("side") or candidate.get("side_hint"),
        {"symbol_sentiment": "neutral"},
    )
    if side == "hold" and candidate.get("side_hint") in {"buy", "sell"}:
        side = str(candidate["side_hint"])
    allocation_role = _term(candidate.get("allocation_role") or candidate.get("role"))
    if allocation_role not in ALLOCATION_ROLES:
        allocation_role = (
            "primary"
            if candidate.get("event_ids") and side != "hold"
            else "watchlist"
        )
    return {
        "symbol": symbol,
        "score": _number(candidate.get("score"), 0.5),
        "side": side,
        "allocation_role": allocation_role,
        "hold_reason": _optional_string(
            candidate.get("hold_reason") or candidate.get("reject_reason")
        ),
        "reason": _string(
            candidate.get("reason") or candidate.get("rationale"),
            f"{symbol} was ranked from deterministic portfolio features.",
        ),
        "evidence_ids": _list(candidate.get("evidence_ids"), []),
        "relationship_notes": _list(
            candidate.get("relationship_notes") or candidate.get("relation_notes"),
            [],
        ),
    }


def _proposal_from_dict(
    value: Any,
    *,
    metadata: dict[str, Any],
    default_symbol: str,
    index: int,
) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    symbol = _string(source.get("symbol") or default_symbol, default_symbol)
    candidates = _candidate_by_symbol(metadata)
    candidate = candidates.get(symbol, {})
    candidate_events = _list(candidate.get("event_ids"), [])
    evidence_ids = _list(source.get("evidence_ids"), candidate_events or _metadata_events(metadata))
    allocation_role = _term(
        source.get("allocation_role") or source.get("role") or candidate.get("allocation_role")
    )
    if allocation_role not in ALLOCATION_ROLES:
        allocation_role = (
            "primary"
            if candidate_events or evidence_ids
            else "watchlist"
        )
    side = _side(
        source.get("side")
        or source.get("action")
        or source.get("direction")
        or candidate.get("side_hint"),
        metadata,
    )
    hold = side == "hold"
    quantity = 0 if hold else max(1, min(5000, _int(source.get("quantity"), 500)))
    score = _number(source.get("confidence") or candidate.get("score"), 0.55)
    return {
        "proposal_id": _string(
            source.get("proposal_id"),
            f"{metadata.get('cycle_id', 'cycle')}-{symbol}-proposal-{index}",
        ),
        "symbol": symbol,
        "side": side,
        "allocation_role": allocation_role if not hold else "watchlist",
        "hold_reason": _optional_string(
            source.get("hold_reason")
            or source.get("reject_reason")
            or candidate.get("hold_reason")
        ),
        "quantity": quantity,
        "max_notional": 0.0 if hold else _float(source.get("max_notional"), 200_000),
        "rationale": _string(
            source.get("rationale") or source.get("message") or candidate.get("reason"),
            "Monitoring only until released evidence or strong cross-ticker score supports a trade."
            if hold
            else f"Proposal is based on the ranked portfolio slate for {symbol}.",
        ),
        "evidence_ids": evidence_ids,
        "confidence": score,
        "evidence_summary": _optional_string(
            source.get("evidence_summary") or source.get("evidence_used")
        ) or _summary_from_evidence(evidence_ids),
        "key_drivers": _list(
            source.get("key_drivers") or source.get("drivers"),
            [_string(candidate.get("reason"), f"{symbol} ranked in the candidate slate.")],
        ),
        "counterpoints": _list(
            source.get("counterpoints") or source.get("risks") or source.get("tradeoffs"),
            ["Basket sizing remains subject to independent risk and committee gates."],
        ),
        "sizing_rationale": _optional_string(source.get("sizing_rationale")) or (
            "No routeable size."
            if hold
            else f"Requested {quantity} shares before risk and committee sizing."
        ),
        "risk_controls": _list(
            source.get("risk_controls") or source.get("controls"),
            ["Max three proposals per cycle", "Independent risk review", "Compliance review"],
        ),
    }


def _unwrap(payload: Any, schema: type[BaseModel]) -> tuple[dict[str, Any], bool]:
    if not isinstance(payload, dict):
        return {}, True
    required = set(schema.model_fields)
    if required & set(payload):
        return dict(payload), False
    for key in (
        "data",
        "result",
        "response",
        "output",
        "payload",
        "report",
        "argument",
        "proposal",
        "decision",
        "message",
        "content",
    ):
        value = payload.get(key)
        if isinstance(value, dict):
            unwrapped, _ = _unwrap(value, schema)
            if unwrapped:
                return unwrapped, True
    return dict(payload), False


def _direction(value: Any, metadata: dict[str, Any]) -> str:
    term = _term(value)
    if term in NEUTRAL_TERMS:
        return "neutral"
    if term in BULL_TERMS:
        return "bullish"
    if term in BEAR_TERMS:
        return "bearish"
    sentiment = _term(metadata.get("symbol_sentiment"))
    if sentiment in {"bullish", "bearish", "neutral"}:
        return sentiment
    if sentiment == "mixed":
        return "neutral"
    return "neutral"


def _stance(value: Any, agent_name: str) -> str:
    term = _term(value)
    if term in NEUTRAL_TERMS:
        return "neutral"
    if term in BULL_TERMS:
        return "bull"
    if term in BEAR_TERMS:
        return "bear"
    if "Bear" in agent_name:
        return "bear"
    if "Bull" in agent_name:
        return "bull"
    return "neutral"


def _side(value: Any, metadata: dict[str, Any]) -> str:
    term = _term(value)
    if term in NEUTRAL_TERMS:
        return "hold"
    if term in BULL_TERMS:
        return "buy"
    if term in BEAR_TERMS:
        return "sell"
    sentiment = _term(metadata.get("symbol_sentiment"))
    if sentiment == "bullish":
        return "buy"
    if sentiment == "bearish":
        return "sell"
    return "hold"


def normalize_payload(
    payload: Any,
    response_schema: type[BaseModel],
    *,
    agent_name: str,
    metadata: dict[str, Any],
) -> tuple[dict[str, Any], bool, str | None]:
    data, changed = _unwrap(payload, response_schema)
    original = dict(data)
    symbol = _string(data.get("symbol") or metadata.get("symbol"), "ALPH")
    evidence_ids = _list(data.get("evidence_ids"), _metadata_events(metadata))

    if response_schema is SignalReport:
        data["agent_id"] = _string(data.get("agent_id"), agent_name)
        data["symbol"] = symbol
        data["direction"] = _direction(data.get("direction") or data.get("signal"), metadata)
        data["confidence"] = _number(data.get("confidence"), 0.5)
        data["evidence_ids"] = evidence_ids
        data["rationale"] = _string(
            data.get("rationale") or data.get("message") or data.get("summary"),
            f"{agent_name} reviewed point-in-time context for {symbol}.",
        )
        uncertainty = data.get("uncertainty")
        data["uncertainty"] = (
            uncertainty
            if isinstance(uncertainty, str)
            else f"Uncertainty score: {_number(uncertainty, 0.5):.2f}."
        )
        data["evidence_summary"] = _optional_string(
            data.get("evidence_summary") or data.get("evidence_used")
        ) or _summary_from_evidence(evidence_ids)
        data["key_drivers"] = _list(
            data.get("key_drivers") or data.get("drivers"),
            [data["rationale"]],
        )
        data["counterpoints"] = _list(
            data.get("counterpoints") or data.get("risks") or data.get("tradeoffs"),
            [data["uncertainty"]],
        )
        data["decision_rationale"] = _optional_string(
            data.get("decision_rationale") or data.get("thesis")
        ) or data["rationale"]
    elif response_schema is DebateArgument:
        data["agent_id"] = _string(data.get("agent_id") or data.get("agent"), agent_name)
        data["stance"] = _stance(data.get("stance") or data.get("direction"), agent_name)
        data["symbol"] = symbol
        data["claim"] = _string(
            data.get("claim")
            or data.get("message")
            or data.get("argument")
            or data.get("rationale")
            or data.get("summary"),
            f"{agent_name} reviewed {symbol} and found limited trade evidence.",
        )
        data["evidence_ids"] = evidence_ids
        data["confidence"] = _number(data.get("confidence"), 0.5)
        data["evidence_summary"] = _optional_string(
            data.get("evidence_summary") or data.get("evidence_used")
        ) or _summary_from_evidence(evidence_ids)
        data["counterpoints"] = _list(
            data.get("counterpoints") or data.get("risks") or data.get("tradeoffs"),
            ["Opposing agents may weigh the same evidence differently."],
        )
        data["decision_rationale"] = _optional_string(
            data.get("decision_rationale") or data.get("rationale")
        ) or data["claim"]
    elif response_schema is TradeProposal:
        side = _side(data.get("side") or data.get("action") or data.get("direction"), metadata)
        hold = side == "hold"
        data["proposal_id"] = _string(
            data.get("proposal_id"),
            metadata.get("proposal_id", f"{metadata.get('cycle_id', 'cycle')}-{symbol}-proposal"),
        )
        data["symbol"] = symbol
        data["side"] = side
        data["quantity"] = 0 if hold else max(1, _int(data.get("quantity"), 100))
        data["max_notional"] = 0.0 if hold else _float(data.get("max_notional"), 200_000)
        data["rationale"] = _string(
            data.get("rationale") or data.get("message") or data.get("summary"),
            "Monitoring only until released evidence supports a trade."
            if hold
            else f"Proposal is based on released {symbol} evidence and orderbook context.",
        )
        data["evidence_ids"] = evidence_ids
        data["confidence"] = _number(data.get("confidence"), 0.5)
        data["evidence_summary"] = _optional_string(
            data.get("evidence_summary") or data.get("evidence_used")
        ) or _summary_from_evidence(evidence_ids)
        data["key_drivers"] = _list(
            data.get("key_drivers") or data.get("drivers"),
            [data["rationale"]],
        )
        data["counterpoints"] = _list(
            data.get("counterpoints") or data.get("risks") or data.get("tradeoffs"),
            ["No trade is allowed without released evidence IDs."]
            if hold
            else ["Sizing remains subject to risk, compliance, liquidity, and committee review."],
        )
        data["sizing_rationale"] = _optional_string(data.get("sizing_rationale")) or (
            "Quantity is zero because the agent is monitoring until released evidence appears."
            if hold
            else f"Requested {data['quantity']} shares within max notional {data['max_notional']}."
        )
        data["risk_controls"] = _list(
            data.get("risk_controls") or data.get("controls"),
            ["Require released evidence IDs", "Pre-trade risk review", "Compliance review"],
        )
    elif response_schema is PortfolioAllocationProposal:
        candidates = _metadata_candidates(metadata)
        candidate_by_symbol = _candidate_by_symbol(metadata)
        proposal_values = data.get("proposals") or data.get("trades") or data.get("orders")
        if not isinstance(proposal_values, list):
            proposal_values = []
        if not proposal_values and any(key in data for key in ("side", "action", "quantity")):
            proposal_values = [data]

        proposals = [
            _proposal_from_dict(
                value,
                metadata=metadata,
                default_symbol=symbol,
                index=index,
            )
            for index, value in enumerate(proposal_values[:3], start=1)
        ]
        if not proposals and candidates:
            for candidate in candidates:
                side_hint = str(candidate.get("side_hint") or "hold")
                score = _number(candidate.get("score"), 0)
                candidate_events = _list(candidate.get("event_ids"), [])
                allocation_role = _term(candidate.get("allocation_role"))
                if allocation_role not in ALLOCATION_ROLES:
                    allocation_role = (
                        "primary"
                        if candidate_events and side_hint in {"buy", "sell"}
                        else "watchlist"
                    )
                basket_events = _metadata_events(metadata)
                has_evidence = bool(candidate_events or basket_events)
                eligible = False
                if side_hint in {"buy", "sell"}:
                    if allocation_role == "primary":
                        eligible = bool(candidate_events)
                    elif allocation_role == "hedge":
                        eligible = has_evidence and score >= 0.16
                    elif allocation_role == "relative_value":
                        eligible = has_evidence and score >= 0.30
                    else:
                        eligible = has_evidence and score >= 0.72
                if eligible:
                    proposals.append(
                        _proposal_from_dict(
                            {
                                "symbol": candidate.get("symbol"),
                                "side": side_hint,
                                "allocation_role": allocation_role,
                                "quantity": max(50, int(350 + score * 1600)),
                                "confidence": score,
                                "evidence_ids": candidate_events or basket_events[-3:],
                                "rationale": candidate.get("reason"),
                            },
                            metadata=metadata,
                            default_symbol=symbol,
                            index=len(proposals) + 1,
                        )
                    )
                    if len(proposals) >= 3:
                        break
        if not proposals:
            proposals = [
                _proposal_from_dict(
                    {"symbol": symbol, "side": "hold", "quantity": 0},
                    metadata=metadata,
                    default_symbol=symbol,
                    index=1,
                )
            ]

        ranked_input = data.get("ranked_candidates") or data.get("candidates") or candidates
        if not isinstance(ranked_input, list):
            ranked_input = []
        ranked = [
            _candidate_summary(item, default_symbol=symbol)
            for item in ranked_input
            if isinstance(item, dict)
        ]
        if not ranked:
            ranked = [_candidate_summary(item, default_symbol=symbol) for item in candidates]
        proposed_symbols = {
            proposal["symbol"] for proposal in proposals if proposal["side"] != "hold"
        }
        rejected_input = data.get("rejected_candidates") or data.get("watchlist") or []
        if isinstance(rejected_input, list) and rejected_input:
            rejected = [
                _candidate_summary(item, default_symbol=symbol)
                for item in rejected_input
                if isinstance(item, dict)
            ]
        else:
            rejected = [
                _candidate_summary(candidate, default_symbol=symbol)
                for candidate_symbol, candidate in candidate_by_symbol.items()
                if candidate_symbol not in proposed_symbols
            ]

        data["allocation_id"] = _string(
            data.get("allocation_id"),
            f"{metadata.get('cycle_id', 'cycle')}-allocation",
        )
        data["proposals"] = proposals[:3]
        data["ranked_candidates"] = ranked
        data["rejected_candidates"] = rejected[:5]
        data["allocation_rationale"] = _string(
            data.get("allocation_rationale")
            or data.get("rationale")
            or data.get("message")
            or data.get("summary"),
            "Ranked the full active ticker slate and selected the strongest simulated basket.",
        )
        data["exposure_notes"] = _list(
            data.get("exposure_notes") or data.get("portfolio_notes"),
            ["Respect per-name, gross, and sector exposure limits."],
        )

    if data != original:
        changed = True
    summary = "Normalized provider JSON to match the expected agent schema." if changed else None
    return data, changed, summary


def validation_summary(exc: Exception) -> str:
    text = str(exc).splitlines()
    return text[0] if text else exc.__class__.__name__


def repair_prompt(
    *,
    response_schema: type[BaseModel],
    validation_error: Exception,
    raw_text: str,
    user_prompt: str,
) -> str:
    schema_json = json.dumps(response_schema.model_json_schema(), indent=2)
    return (
        "Return only one JSON object that validates against this JSON schema.\n"
        "Use exactly the enum values in the schema. Do not include markdown.\n\n"
        f"JSON schema:\n{schema_json[:7000]}\n\n"
        f"Validation error summary: {validation_summary(validation_error)}\n\n"
        f"Original user context:\n{user_prompt[:4000]}\n\n"
        f"Invalid model output:\n{raw_text[:2500]}"
    )
