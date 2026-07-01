from __future__ import annotations

import asyncio
import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypeVar

from pydantic import BaseModel

from app.agents.model_router import LLMModelRouter
from app.agents.providers import LLMProvider, LLMResult, MockLLMProvider
from app.observability.metrics import (
    agent_failures_total,
    agent_runs_total,
    llm_calls_total,
    llm_latency_ms,
    llm_tokens_total,
    qwen_calls_total,
    qwen_latency_ms,
    qwen_tokens_total,
)
from app.schemas.agent_outputs import (
    DebateArgument,
    PortfolioAllocationProposal,
    SignalReport,
    TradeProposal,
)
from app.schemas.market import (
    AgentDecisionTrace,
    AgentState,
    ConflictRecord,
    ConsensusSnapshot,
    DebateMessage,
)
from app.services.compliance_service import ComplianceService
from app.services.context_packer import ContextPacker
from app.services.investment_committee_service import InvestmentCommitteeService
from app.services.risk_service import RiskService
from app.skills.mcp_adapter import LocalMCPAdapter
from app.skills.qwen_tool_adapter import QwenToolGateway
from app.skills.registry import SkillRegistry
from app.skills.schemas import SkillCallRecord

BlockingResult = TypeVar("BlockingResult")


@dataclass(slots=True)
class AgentCycleResult:
    agent_states: list[AgentState]
    debate: list[DebateMessage]
    conflicts: list[ConflictRecord]
    consensus: list[ConsensusSnapshot]
    proposal: TradeProposal
    proposals: list[TradeProposal]
    allocation: PortfolioAllocationProposal
    decision_traces: list[AgentDecisionTrace]
    llm_results: list[LLMResult]
    tool_records: list[SkillCallRecord]


class AgentOrchestrator:
    def __init__(
        self,
        *,
        registry: SkillRegistry,
        risk_service: RiskService,
        compliance_service: ComplianceService,
        committee_service: InvestmentCommitteeService,
        provider: LLMProvider,
        model_router: LLMModelRouter,
        context_packer: ContextPacker,
        tool_gateway: QwenToolGateway,
        mcp_adapter: LocalMCPAdapter,
        max_parallel_agent_calls: int = 5,
    ) -> None:
        self.registry = registry
        self.risk_service = risk_service
        self.compliance_service = compliance_service
        self.committee_service = committee_service
        self.provider = provider
        self.fallback_provider = MockLLMProvider()
        self.model_router = model_router
        self.context_packer = context_packer
        self.tool_gateway = tool_gateway
        self.mcp_adapter = mcp_adapter
        self.max_parallel_agent_calls = max(1, max_parallel_agent_calls)

    def produce_cycle(
        self,
        *,
        simulation_id: str,
        cycle_id: str,
        timestamp: datetime,
        symbol: str,
        event_ids: list[str],
        symbol_sentiment: str,
        context: dict[str, Any],
        candidate_slate: list[dict[str, Any]] | None = None,
        candidate_symbols: list[str] | None = None,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> AgentCycleResult:
        candidate_slate = candidate_slate or []
        candidate_symbols = candidate_symbols or [symbol]
        all_event_ids = sorted(
            {
                *event_ids,
                *(
                    str(event_id)
                    for candidate in candidate_slate
                    for event_id in candidate.get("event_ids", [])
                ),
            }
        )
        tool_records = self._collect_context_tools(
            simulation_id=simulation_id,
            cycle_id=cycle_id,
            symbols=candidate_symbols,
        )
        tool_context = {
            record.skill_name: record.output_json or record.error_json or {}
            for record in tool_records
        }
        base_context = {
            "timestamp": timestamp.isoformat(),
            "symbol": symbol,
            "symbol_sentiment": symbol_sentiment,
            "released_evidence_ids": all_event_ids,
            "candidate_symbols": candidate_symbols,
            "candidate_slate": candidate_slate,
            "visible_context": context,
            "tool_outputs": tool_context,
        }
        packed_context = self.context_packer.pack(base_context)
        metadata = {
            "cycle_id": cycle_id,
            "symbol": symbol,
            "symbol_sentiment": symbol_sentiment,
            "event_ids": all_event_ids,
            "proposal_id": f"{cycle_id}-{symbol}-proposal",
            "candidate_slate": candidate_slate,
            "candidate_symbols": candidate_symbols,
            "max_proposals": 3,
        }

        if progress_callback:
            progress_callback(
                {
                    "phase": "group_started",
                    "agent": "Research pod",
                    "provider": getattr(self.provider, "provider_name", "unknown"),
                    "model": None,
                    "error": None,
                }
            )
        research_results = self._complete_many(
            [
                ("MacroAnalystAgent", "macro analyst", SignalReport),
                (
                    "TechnicalAnalystAgent",
                    "technical and order-book analyst",
                    SignalReport,
                ),
                ("SentimentNewsAnalystAgent", "news and event analyst", SignalReport),
                ("BullResearcherAgent", "pro-trade debater", DebateArgument),
                ("BearResearcherAgent", "contra-trade debater", DebateArgument),
            ],
            packed_context,
            metadata,
            progress_callback,
        )
        macro = research_results["MacroAnalystAgent"]
        technical = research_results["TechnicalAnalystAgent"]
        sentiment = research_results["SentimentNewsAnalystAgent"]
        bull = research_results["BullResearcherAgent"]
        bear = research_results["BearResearcherAgent"]

        reports = [
            SignalReport.model_validate(macro.content_json),
            SignalReport.model_validate(technical.content_json),
            SignalReport.model_validate(sentiment.content_json),
        ]
        bull_argument = DebateArgument.model_validate(bull.content_json)
        bear_argument = DebateArgument.model_validate(bear.content_json)
        consensus_symbol = "PORTFOLIO" if len(candidate_symbols) > 1 else symbol
        consensus = self._consensus(consensus_symbol, reports, bull_argument, bear_argument)
        portfolio_context = self.context_packer.pack(
            {
                **base_context,
                "research_outputs": {
                    "signals": [report.model_dump(mode="json") for report in reports],
                    "debate": [
                        bull_argument.model_dump(mode="json"),
                        bear_argument.model_dump(mode="json"),
                    ],
                    "consensus": consensus[0].model_dump(mode="json"),
                },
                "coordination_instruction": (
                    "Rank the full candidate slate. Propose at most three simulated trades "
                    "as an evidence-led basket. Use allocation_role=primary for direct "
                    "catalyst trades, hedge for small portfolio hedges, relative_value for "
                    "strong related opportunities, and watchlist for holds. Do not trade "
                    "watchlist names."
                ),
            }
        )
        proposal_result = self._complete(
            "PortfolioManagerAgent",
            "portfolio manager",
            portfolio_context,
            PortfolioAllocationProposal,
            metadata,
            progress_callback,
        )
        allocation = PortfolioAllocationProposal.model_validate(proposal_result.content_json)
        allocation = self._sanitize_allocation(
            allocation=allocation,
            cycle_id=cycle_id,
            primary_symbol=symbol,
            event_ids=all_event_ids,
            candidate_slate=candidate_slate,
        )
        proposals = allocation.proposals
        proposal = proposals[0]

        debate = [
            DebateMessage(
                id=f"{cycle_id}-bull",
                timestamp=timestamp,
                agent_id=bull_argument.agent_id,
                stance=bull_argument.stance,
                message=bull_argument.claim,
                evidence_ids=[item for item in bull_argument.evidence_ids if item in all_event_ids],
                symbol=consensus_symbol,
            ),
            DebateMessage(
                id=f"{cycle_id}-bear",
                timestamp=timestamp,
                agent_id=bear_argument.agent_id,
                stance=bear_argument.stance,
                message=bear_argument.claim,
                evidence_ids=[item for item in bear_argument.evidence_ids if item in all_event_ids],
                symbol=consensus_symbol,
            ),
        ]
        disagreement = consensus[0].disagreement_score
        conflicts = [
            ConflictRecord(
                id=f"{cycle_id}-debate-conflict",
                conflict_type="Research disagreement",
                issue=f"Bull and bear researchers disagree at {round(disagreement * 100)}%.",
                agents_involved=[
                    "BullResearcherAgent",
                    "BearResearcherAgent",
                    "InvestmentCommitteeChairAgent",
                ],
                proposed_solution=(
                    "Escalate to committee with deterministic risk and compliance checks."
                ),
                final_decision="committee_review",
                winning_constraint="committee protocol",
            )
        ]
        llm_results = [macro, technical, sentiment, bull, bear, proposal_result]
        agent_states = self._agent_states(
            symbol=symbol,
            proposal=proposal,
            proposals=proposals,
            allocation=allocation,
            reports=reports,
            bull=bull_argument,
            bear=bear_argument,
            llm_results=llm_results,
        )
        decision_traces = self._decision_traces(
            cycle_id=cycle_id,
            timestamp=timestamp,
            symbol=symbol,
            proposal=proposal,
            proposals=proposals,
            allocation=allocation,
            reports=reports,
            bull=bull_argument,
            bear=bear_argument,
            consensus=consensus[0],
            tool_records=tool_records,
        )
        return AgentCycleResult(
            agent_states=agent_states,
            debate=debate,
            conflicts=conflicts,
            consensus=consensus,
            proposal=proposal,
            proposals=proposals,
            allocation=allocation,
            decision_traces=decision_traces,
            llm_results=llm_results,
            tool_records=tool_records,
        )

    def _sanitize_allocation(
        self,
        *,
        allocation: PortfolioAllocationProposal,
        cycle_id: str,
        primary_symbol: str,
        event_ids: list[str],
        candidate_slate: list[dict[str, Any]],
    ) -> PortfolioAllocationProposal:
        candidate_events = {
            str(candidate.get("symbol")): [
                str(event_id) for event_id in candidate.get("event_ids", [])
            ]
            for candidate in candidate_slate
            if candidate.get("symbol")
        }
        candidate_by_symbol = {
            str(candidate.get("symbol")): candidate
            for candidate in candidate_slate
            if candidate.get("symbol")
        }
        allowed_symbols = {primary_symbol, *candidate_events}
        allowed_events = set(event_ids)
        for symbol_events in candidate_events.values():
            allowed_events.update(symbol_events)
        sanitized: list[TradeProposal] = []
        seen_symbols: set[str] = set()
        role_counts = {"primary": 0, "hedge": 0, "relative_value": 0}
        for raw_proposal in allocation.proposals[:3]:
            proposal = raw_proposal.model_copy(deep=True)
            if proposal.symbol not in allowed_symbols:
                proposal.symbol = primary_symbol
            if proposal.symbol in seen_symbols:
                continue
            candidate = candidate_by_symbol.get(proposal.symbol, {})
            symbol_events = candidate_events.get(proposal.symbol, [])
            candidate_side = str(candidate.get("side_hint") or "hold")
            candidate_role = str(
                candidate.get("allocation_role")
                or (
                    "primary"
                    if symbol_events and candidate_side in {"buy", "sell"}
                    else "watchlist"
                )
            )
            if candidate_role in {"hedge", "relative_value"}:
                proposal.allocation_role = candidate_role  # type: ignore[assignment]
            elif candidate_role == "primary" and proposal.side != "hold":
                proposal.allocation_role = "primary"
            if proposal.side == "hold" or candidate_role == "watchlist":
                proposal.side = "hold"
                proposal.quantity = 0
                proposal.max_notional = 0.0
                proposal.allocation_role = "watchlist"
                proposal.hold_reason = proposal.hold_reason or candidate.get("hold_reason")
            if (
                proposal.allocation_role in role_counts
                and role_counts[proposal.allocation_role] >= (
                    1 if proposal.allocation_role in {"hedge", "relative_value"} else 3
                )
            ):
                continue
            seen_symbols.add(proposal.symbol)
            proposal.proposal_id = f"{cycle_id}-{proposal.symbol}-proposal-{len(sanitized) + 1}"
            symbol_events = candidate_events.get(proposal.symbol, [])
            proposal.evidence_ids = [
                evidence_id
                for evidence_id in proposal.evidence_ids
                if evidence_id in allowed_events
            ]
            if not proposal.evidence_ids and symbol_events:
                proposal.evidence_ids = symbol_events[-3:]
            if (
                not proposal.evidence_ids
                and proposal.allocation_role in {"hedge", "relative_value"}
            ):
                proposal.evidence_ids = event_ids[-3:]
            if proposal.side == "hold":
                proposal.quantity = 0
                proposal.max_notional = 0.0
            else:
                proposal.quantity = max(1, min(proposal.quantity, 5000))
            if proposal.allocation_role in role_counts and proposal.side != "hold":
                role_counts[proposal.allocation_role] += 1
            sanitized.append(proposal)
        if not sanitized:
            sanitized.append(
                TradeProposal(
                    proposal_id=f"{cycle_id}-{primary_symbol}-proposal-1",
                    symbol=primary_symbol,
                    side="hold",
                    allocation_role="watchlist",
                    hold_reason="no candidate cleared gates",
                    quantity=0,
                    max_notional=0.0,
                    rationale="No candidate cleared the allocation gates.",
                    evidence_ids=event_ids[-3:],
                    confidence=0.5,
                    evidence_summary=(
                        "No routeable portfolio allocation was produced by the PM step."
                    ),
                    key_drivers=["Candidate slate stayed below trade threshold."],
                    counterpoints=["Opportunity cost of staying in cash."],
                    sizing_rationale="No simulated order size.",
                    risk_controls=["Maintain cash until evidence improves."],
                )
            )
        allocation.proposals = sanitized[:3]
        return allocation

    def _collect_context_tools(
        self, *, simulation_id: str, cycle_id: str, symbols: list[str]
    ) -> list[SkillCallRecord]:
        records: list[SkillCallRecord] = []
        symbols = symbols or []
        records.extend(
            self.tool_gateway.execute_tool_calls(
                tool_calls=[{"name": "market_get_snapshot", "arguments": {"symbols": symbols}}],
                simulation_id=simulation_id,
                cycle_id=cycle_id,
                agent_id="MacroAnalystAgent",
            )
        )
        records.extend(
            self.tool_gateway.execute_tool_calls(
                tool_calls=[
                    {"name": "news_get_released_events", "arguments": {"symbols": symbols}},
                ],
                simulation_id=simulation_id,
                cycle_id=cycle_id,
                agent_id="SentimentNewsAnalystAgent",
            )
        )
        records.extend(
            self.tool_gateway.execute_tool_calls(
                tool_calls=[
                    tool_call
                    for candidate_symbol in symbols[:5]
                    for tool_call in (
                        {
                            "name": "orderbook_get_depth",
                            "arguments": {"symbol": candidate_symbol, "depth": 5},
                        },
                        {
                            "name": "research_compute_indicators",
                            "arguments": {
                                "symbol": candidate_symbol,
                                "lookback_minutes": 15,
                            },
                        },
                    )
                ],
                simulation_id=simulation_id,
                cycle_id=cycle_id,
                agent_id="TechnicalAnalystAgent",
            )
        )
        records.append(
            self.mcp_adapter.call_tool(
                tool_name="portfolio_get_state",
                arguments={},
                simulation_id=simulation_id,
                cycle_id=cycle_id,
                agent_id="ResearchManagerAgent",
            )
        )
        return records

    def _complete_many(
        self,
        calls: list[tuple[str, str, type[BaseModel]]],
        user_prompt: str,
        metadata: dict[str, Any],
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, LLMResult]:
        return self._await_blocking(
            self._complete_many_async(calls, user_prompt, metadata, progress_callback)
        )

    async def _complete_many_async(
        self,
        calls: list[tuple[str, str, type[BaseModel]]],
        user_prompt: str,
        metadata: dict[str, Any],
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, LLMResult]:
        if len(calls) <= 1 or self.max_parallel_agent_calls <= 1:
            results: dict[str, LLMResult] = {}
            for agent_name, role, response_schema in calls:
                results[agent_name] = await self._complete_async(
                    agent_name,
                    role,
                    user_prompt,
                    response_schema,
                    metadata,
                    progress_callback,
                )
            return results

        semaphore = asyncio.Semaphore(self.max_parallel_agent_calls)

        async def run_call(
            agent_name: str,
            role: str,
            response_schema: type[BaseModel],
        ) -> tuple[str, LLMResult]:
            async with semaphore:
                return (
                    agent_name,
                    await self._complete_async(
                        agent_name,
                        role,
                        user_prompt,
                        response_schema,
                        metadata,
                        progress_callback,
                    ),
                )

        completed = await asyncio.gather(
            *(
                run_call(agent_name, role, response_schema)
                for agent_name, role, response_schema in calls
            )
        )
        return dict(completed)

    def _complete(
        self,
        agent_name: str,
        role: str,
        user_prompt: str,
        response_schema: type[BaseModel],
        metadata: dict[str, Any],
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> LLMResult:
        return self._await_blocking(
            self._complete_async(
                agent_name,
                role,
                user_prompt,
                response_schema,
                metadata,
                progress_callback,
            )
        )

    async def _complete_async(
        self,
        agent_name: str,
        role: str,
        user_prompt: str,
        response_schema: type[BaseModel],
        metadata: dict[str, Any],
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> LLMResult:
        model, temperature = self.model_router.route(agent_name)
        system_prompt = (
            f"You are {agent_name}, the {role} in a simulated hedge-fund agent society. "
            "Use only the point-in-time context and tool outputs. Return strict JSON matching "
            "the requested schema. Do not include hidden chain-of-thought. Provide concise "
            "decision reasoning with evidence IDs, key drivers, assumptions, trade-offs, risk "
            "controls, dissent or counterpoints, and why the proposed action, size, or no-action "
            "follows from visible context."
        )
        if response_schema is TradeProposal:
            system_prompt += (
                ' If there are no released_evidence_ids, return side "hold", quantity 0, '
                "and explain that the agent is monitoring until released evidence appears."
            )
        if response_schema is PortfolioAllocationProposal:
            system_prompt += (
                " Return one portfolio allocation object. Include at most three proposals. "
                "Rank all candidate_slate entries, reject/watchlist weaker candidates, and "
                "state exposure notes. If no candidate clears evidence or strong-score gates, "
                'return one hold proposal with quantity 0.'
            )
        call_metadata = {**metadata, "model": model}
        if progress_callback:
            progress_callback(
                {
                    "phase": "started",
                    "agent": agent_name,
                    "provider": getattr(self.provider, "provider_name", "unknown"),
                    "model": model,
                    "error": None,
                    "role": role,
                    "temperature": temperature,
                    "max_tokens": 900,
                    "system_prompt": system_prompt,
                    "user_prompt": user_prompt,
                    "response_schema": response_schema.model_json_schema(),
                    "metadata": call_metadata,
                }
            )
        try:
            result = await self.provider.complete_json(
                agent_name=agent_name,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_schema=response_schema,
                temperature=temperature,
                max_tokens=900,
                metadata=call_metadata,
            )
            agent_runs_total.labels(agent=agent_name).inc()
        except Exception as exc:
            agent_failures_total.labels(agent=agent_name).inc()
            error_summary = self._fallback_error_summary(exc)
            error_category = self._fallback_error_category(exc)
            if progress_callback:
                progress_callback(
                    {
                        "phase": "fallback",
                        "agent": agent_name,
                        "provider": getattr(self.fallback_provider, "provider_name", "mock"),
                        "model": "mock-deterministic",
                        "error": error_summary,
                        "exception_type": exc.__class__.__name__,
                        "error_category": error_category,
                        "role": role,
                        "temperature": temperature,
                        "max_tokens": 900,
                        "system_prompt": system_prompt,
                        "user_prompt": user_prompt,
                        "response_schema": response_schema.model_json_schema(),
                        "metadata": call_metadata,
                    }
                )
            result = await self.fallback_provider.complete_json(
                agent_name=agent_name,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_schema=response_schema,
                temperature=0,
                max_tokens=900,
                metadata=call_metadata,
            )
        llm_calls_total.labels(provider=result.provider).inc()
        llm_latency_ms.labels(provider=result.provider).observe(result.latency_ms)
        llm_tokens_total.labels(provider=result.provider).inc(result.total_tokens)
        if result.provider == "qwen":
            qwen_calls_total.inc()
            qwen_latency_ms.observe(result.latency_ms)
            qwen_tokens_total.inc(result.total_tokens)
        if progress_callback:
            progress_callback(
                {
                    "phase": "completed",
                    "agent": agent_name,
                    "provider": result.provider,
                    "model": result.model,
                    "error": None,
                    "repair_status": result.repair_status,
                    "validation_summary": result.validation_summary,
                    "role": role,
                    "temperature": temperature,
                    "max_tokens": 900,
                    "system_prompt": system_prompt,
                    "user_prompt": user_prompt,
                    "response_schema": response_schema.model_json_schema(),
                    "metadata": call_metadata,
                    "raw_text": result.raw_text,
                    "content_json": result.content_json,
                    "prompt_tokens": result.prompt_tokens,
                    "completion_tokens": result.completion_tokens,
                    "total_tokens": result.total_tokens,
                    "latency_ms": result.latency_ms,
                }
            )
        return result

    def _fallback_error_summary(self, exc: Exception) -> str:
        text = str(exc).splitlines()
        if not text:
            return "Provider output failed after schema repair; mock fallback used."
        first = text[0]
        if "validation error" in first.lower():
            return f"Provider output failed schema validation after repair: {first}"
        return first[:240]

    def _fallback_error_category(self, exc: Exception) -> str:
        name = exc.__class__.__name__.lower()
        message = str(exc).lower()
        if any(term in name or term in message for term in ("connection", "connect", "timeout")):
            return "connection"
        if any(term in name for term in ("ratelimit", "status", "apierror", "authentication")):
            return "api"
        if any(term in name or term in message for term in ("validation", "json", "schema")):
            return "schema"
        return "provider"

    def _await_blocking(self, awaitable: Awaitable[BlockingResult]) -> BlockingResult:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(awaitable)

        result: BlockingResult | None = None
        error: BaseException | None = None

        def run_in_thread() -> None:
            nonlocal result, error
            try:
                result = asyncio.run(awaitable)
            except BaseException as exc:  # pragma: no cover - defensive bridge
                error = exc

        thread = threading.Thread(target=run_in_thread, daemon=True)
        thread.start()
        thread.join()
        if error:
            raise error
        if result is None:  # pragma: no cover - defensive bridge
            raise RuntimeError("Agent provider returned no result.")
        return result

    def _consensus(
        self,
        symbol: str,
        reports: list[SignalReport],
        bull: DebateArgument,
        bear: DebateArgument,
    ) -> list[ConsensusSnapshot]:
        bullish = sum(report.confidence for report in reports if report.direction == "bullish")
        bearish = sum(report.confidence for report in reports if report.direction == "bearish")
        neutral = sum(report.confidence for report in reports if report.direction == "neutral")
        if bull.stance == "bull":
            bullish += bull.confidence * 0.5
        if bear.stance == "bear":
            bearish += bear.confidence * 0.5
        total = max(0.01, bullish + bearish + neutral)
        if bullish > bearish and bullish > neutral:
            direction = "bullish"
            strength = bullish / total
        elif bearish > bullish and bearish > neutral:
            direction = "bearish"
            strength = bearish / total
        else:
            direction = "neutral"
            strength = neutral / total
        disagreement = 1 - (abs(bullish - bearish) / max(0.01, bullish + bearish))
        return [
            ConsensusSnapshot(
                symbol=symbol,
                consensus_direction=direction,  # type: ignore[arg-type]
                consensus_strength=round(strength, 2),
                disagreement_score=round(max(0.0, min(1.0, disagreement)), 2),
                uncertainty_score=round(1 - min(0.9, strength), 2),
                movers=["ResearchManagerAgent", "RiskManagerAgent", "BearResearcherAgent"],
            )
        ]

    def _agent_states(
        self,
        *,
        symbol: str,
        proposal: TradeProposal,
        proposals: list[TradeProposal],
        allocation: PortfolioAllocationProposal,
        reports: list[SignalReport],
        bull: DebateArgument,
        bear: DebateArgument,
        llm_results: list[LLMResult],
    ) -> list[AgentState]:
        models = {
            agent: result.model
            for agent, result in zip(
                [
                    "MacroAnalystAgent",
                    "TechnicalAnalystAgent",
                    "SentimentNewsAnalystAgent",
                    "BullResearcherAgent",
                    "BearResearcherAgent",
                    "PortfolioManagerAgent",
                ],
                llm_results,
                strict=True,
            )
        }
        report_by_agent = {report.agent_id: report for report in reports}
        macro = report_by_agent.get("MacroAnalystAgent", reports[0])
        technical = report_by_agent.get("TechnicalAnalystAgent", reports[1])
        sentiment = report_by_agent.get("SentimentNewsAnalystAgent", reports[2])
        trade_proposals = [item for item in proposals if item.side != "hold" and item.quantity > 0]
        basket_text = (
            ", ".join(
                f"{item.allocation_role.replace('_', ' ')} {item.side} "
                f"{item.quantity:,} {item.symbol}"
                for item in trade_proposals
            )
            if trade_proposals
            else "monitor the slate"
        )
        return [
            AgentState(
                agent_id="CoordinatorAgent",
                role="task decomposition",
                status="complete",
                last_action=(
                    "Assigned analysts, debate, PM, risk, compliance, and execution "
                    f"for the portfolio slate led by {symbol}."
                ),
                confidence=0.91,
                model="deterministic-coordinator",
                target_symbol=symbol,
                decision="decompose",
                evidence_ids=proposal.evidence_ids,
            ),
            self._state_from_report(macro, "macro analysis", models["MacroAnalystAgent"]),
            self._state_from_report(
                technical, "technical/orderbook analysis", models["TechnicalAnalystAgent"]
            ),
            self._state_from_report(
                sentiment, "news analysis", models["SentimentNewsAnalystAgent"]
            ),
            AgentState(
                agent_id=bull.agent_id,
                role="pro debate",
                status="complete",
                last_action=bull.claim,
                confidence=bull.confidence,
                model=models["BullResearcherAgent"],
                target_symbol=symbol,
                decision=bull.stance,
                evidence_ids=bull.evidence_ids,
            ),
            AgentState(
                agent_id=bear.agent_id,
                role="contra debate",
                status="complete",
                last_action=bear.claim,
                confidence=bear.confidence,
                model=models["BearResearcherAgent"],
                target_symbol=symbol,
                decision=bear.stance,
                evidence_ids=bear.evidence_ids,
            ),
            AgentState(
                agent_id="PortfolioManagerAgent",
                role="portfolio allocation",
                status="complete",
                last_action=f"Proposed basket: {basket_text}.",
                confidence=proposal.confidence,
                model=models["PortfolioManagerAgent"],
                target_symbol=symbol,
                decision="basket" if trade_proposals else "hold",
                quantity=sum(item.quantity for item in trade_proposals),
                evidence_ids=sorted(
                    {
                        evidence_id
                        for item in proposals
                        for evidence_id in item.evidence_ids
                    }
                ),
            ),
            AgentState(
                agent_id="RiskManagerAgent",
                role="risk constraints",
                status="queued",
                last_action="Waiting for independent pre-trade risk checks per proposal.",
                confidence=0.83,
                model="deterministic-service",
                target_symbol=symbol,
                decision="risk_check",
                quantity=sum(item.quantity for item in trade_proposals),
                evidence_ids=proposal.evidence_ids,
            ),
            AgentState(
                agent_id="ComplianceOfficerAgent",
                role="compliance audit",
                status="queued",
                last_action="Waiting for evidence relevance and leakage checks per proposal.",
                confidence=0.88,
                model="deterministic-service",
                target_symbol=symbol,
                decision="compliance_check",
                evidence_ids=proposal.evidence_ids,
            ),
            AgentState(
                agent_id="InvestmentCommitteeChairAgent",
                role="conflict resolution",
                status="queued",
                last_action=(
                    "Will resolve the proposed basket after risk, compliance, and "
                    "execution checks."
                ),
                confidence=0.8,
                model="committee-protocol",
                target_symbol=symbol,
                decision="committee_review",
                quantity=proposal.quantity,
                evidence_ids=proposal.evidence_ids,
            ),
            AgentState(
                agent_id="ExecutionTraderAgent",
                role="execution planning",
                status="queued",
                last_action="Waiting for broker approvals before routing the basket.",
                confidence=0.78,
                model="fast-llm-or-service",
                target_symbol=symbol,
                decision=proposal.side,
                quantity=proposal.quantity,
                evidence_ids=proposal.evidence_ids,
            ),
        ]

    def _state_from_report(self, report: SignalReport, role: str, model: str) -> AgentState:
        return AgentState(
            agent_id=report.agent_id,
            role=role,
            status="complete",
            last_action=report.rationale,
            confidence=report.confidence,
            model=model,
            target_symbol=report.symbol,
            decision=report.direction,
            evidence_ids=report.evidence_ids,
        )

    def _decision_traces(
        self,
        *,
        cycle_id: str,
        timestamp: datetime,
        symbol: str,
        proposal: TradeProposal,
        proposals: list[TradeProposal],
        allocation: PortfolioAllocationProposal,
        reports: list[SignalReport],
        bull: DebateArgument,
        bear: DebateArgument,
        consensus: ConsensusSnapshot,
        tool_records: list[SkillCallRecord],
    ) -> list[AgentDecisionTrace]:
        traces = [
            AgentDecisionTrace(
                id=f"{cycle_id}-{report.agent_id}-signal",
                cycle_id=cycle_id,
                timestamp=timestamp,
                agent_id=report.agent_id,
                stage="signal",
                symbol=symbol,
                action=report.direction,
                status="complete",
                rationale=report.rationale,
                evidence_ids=report.evidence_ids,
                tool_call_ids=[
                    record.id for record in tool_records if record.agent_id == report.agent_id
                ],
            )
            for report in reports
        ]
        traces.extend(
            [
                AgentDecisionTrace(
                    id=f"{cycle_id}-{bull.agent_id}-debate",
                    cycle_id=cycle_id,
                    timestamp=timestamp,
                    agent_id=bull.agent_id,
                    stage="debate",
                    symbol=symbol,
                    action=bull.stance,
                    status="complete",
                    rationale=bull.claim,
                    evidence_ids=bull.evidence_ids,
                ),
                AgentDecisionTrace(
                    id=f"{cycle_id}-{bear.agent_id}-debate",
                    cycle_id=cycle_id,
                    timestamp=timestamp,
                    agent_id=bear.agent_id,
                    stage="debate",
                    symbol=symbol,
                    action=bear.stance,
                    status="complete",
                    rationale=bear.claim,
                    evidence_ids=bear.evidence_ids,
                ),
                AgentDecisionTrace(
                    id=f"{cycle_id}-consensus",
                    cycle_id=cycle_id,
                    timestamp=timestamp,
                    agent_id="ResearchManagerAgent",
                    stage="consensus",
                    symbol=consensus.symbol,
                    action=consensus.consensus_direction,
                    status="complete",
                    rationale=(
                        f"Consensus {round(consensus.consensus_strength * 100)}%, "
                        f"disagreement {round(consensus.disagreement_score * 100)}%."
                    ),
                    evidence_ids=sorted(
                        {
                            evidence_id
                            for item in proposals
                            for evidence_id in item.evidence_ids
                        }
                    ),
                    tool_call_ids=[
                        record.id
                        for record in tool_records
                        if record.agent_id == "ResearchManagerAgent"
                    ],
                ),
            ]
        )
        traces.extend(
            AgentDecisionTrace(
                id=f"{cycle_id}-proposal-{index}-{item.symbol}",
                cycle_id=cycle_id,
                timestamp=timestamp,
                agent_id="PortfolioManagerAgent",
                stage="proposal",
                symbol=item.symbol,
                action=item.side,
                requested_quantity=item.quantity,
                status="proposed" if item.side != "hold" else "no_trade",
                rationale=item.rationale,
                evidence_ids=item.evidence_ids,
            )
            for index, item in enumerate(proposals, start=1)
        )
        if len(proposals) > 1:
            traces.append(
                AgentDecisionTrace(
                    id=f"{cycle_id}-allocation",
                    cycle_id=cycle_id,
                    timestamp=timestamp,
                    agent_id="PortfolioManagerAgent",
                    stage="allocation",
                    symbol="PORTFOLIO",
                    action="ranked_slate",
                    status="complete",
                    rationale=allocation.allocation_rationale,
                    evidence_ids=sorted(
                        {
                            evidence_id
                            for item in proposals
                            for evidence_id in item.evidence_ids
                        }
                    ),
                )
            )
        return traces
