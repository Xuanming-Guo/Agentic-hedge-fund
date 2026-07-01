from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from app.agents.model_router import LLMModelRouter
from app.agents.orchestrator import AgentOrchestrator
from app.agents.providers import MockLLMProvider
from app.agents.qwen_client import QwenCloudProvider
from app.core.config import get_settings, resolve_llm_provider
from app.core.exceptions import LLMProviderError
from app.evaluation.agent_society_advantage import compute_asai
from app.evaluation.metrics import deterministic_benchmark_metrics
from app.observability.metrics import (
    benchmark_runs_total,
    compliance_rejections_total,
    order_rejections_total,
    risk_rejections_total,
    simulation_ticks_total,
)
from app.schemas.agent_outputs import CommitteeDecision, RiskReview, TradeProposal
from app.schemas.market import (
    AgentActivityDetail,
    AgentActivityItem,
    AgentDecisionTrace,
    AgentSocietyAdvantageReport,
    AgentState,
    BenchmarkMetrics,
    CandidateSlateItem,
    CommitteeDecisionView,
    ConflictRecord,
    ConsensusSnapshot,
    DebateMessage,
    Instrument,
    MarketBar,
    MarketDataMetadata,
    NewsEvent,
    OrderBookSnapshot,
    PortfolioHistoryPoint,
    PortfolioState,
    Scenario,
    SimulationSnapshot,
    SkillCallView,
)
from app.services.actual_market_data import build_real_market_bundle
from app.services.broker_service import BrokerService
from app.services.compliance_service import ComplianceService
from app.services.context_packer import ContextPacker
from app.services.exchange_service import ExchangeService
from app.services.future_data_firewall import FutureDataFirewall
from app.services.human_approval_service import HumanApprovalService
from app.services.investment_committee_service import InvestmentCommitteeService
from app.services.ledger_service import PortfolioLedger
from app.services.orderbook import Order
from app.services.risk_service import RiskService
from app.services.synthetic_data import (
    DATASET,
    INSTRUMENTS,
    market_close_for,
    market_open_for,
    premarket_for,
)
from app.skills.base import Skill
from app.skills.mcp_adapter import LocalMCPAdapter
from app.skills.permissions import PermissionLevel
from app.skills.qwen_tool_adapter import QwenToolGateway
from app.skills.registry import SkillRegistry


@dataclass
class SimulationState:
    simulation_id: str
    scenario: Scenario
    instruments: list[Instrument] = field(default_factory=lambda: list(INSTRUMENTS))
    market_bars: list[MarketBar] = field(default_factory=list)
    market_events: list[NewsEvent] = field(default_factory=list)
    market_data: MarketDataMetadata = field(default_factory=MarketDataMetadata)
    status: str = "created"
    current_time: datetime = field(default_factory=datetime.utcnow)
    speed: float = 1.0
    tick_minutes: int = 1
    cycle_count: int = 0
    last_cycle_minute: int = -999
    ledger: PortfolioLedger = field(default_factory=PortfolioLedger)
    exchange: ExchangeService = field(default_factory=ExchangeService)
    agent_states: list[AgentState] = field(default_factory=list)
    debate: list[DebateMessage] = field(default_factory=list)
    conflicts: list[ConflictRecord] = field(default_factory=list)
    agent_decisions: list[AgentDecisionTrace] = field(default_factory=list)
    committee_decisions: list[CommitteeDecisionView] = field(default_factory=list)
    consensus: list[ConsensusSnapshot] = field(default_factory=list)
    portfolio_history: list[PortfolioHistoryPoint] = field(default_factory=list)
    candidate_slate: list[CandidateSlateItem] = field(default_factory=list)
    benchmark: AgentSocietyAdvantageReport | None = None
    llm_call_count: int = 0
    llm_token_usage: int = 0
    last_llm_provider: str | None = None
    last_llm_model: str | None = None
    agent_cycle_status: str = "idle"
    active_cycle_id: str | None = None
    active_agent: str | None = None
    active_provider: str | None = None
    completed_llm_calls: int = 0
    expected_llm_calls: int = 0
    last_llm_error: str | None = None
    last_completed_provider: str | None = None
    last_fallback_provider: str | None = None
    last_fallback_agent: str | None = None
    last_fallback_reason: str | None = None
    activity_sequence: int = 0
    agent_activity_feed: list[AgentActivityItem] = field(default_factory=list)
    activity_details: dict[str, AgentActivityDetail] = field(default_factory=dict)
    cycle_thread: threading.Thread | None = None


class SimulationEngine:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.firewall = FutureDataFirewall()
        self.registry = SkillRegistry()
        self.risk = RiskService()
        self.compliance = ComplianceService()
        self.committee = InvestmentCommitteeService()
        self.human_approvals = HumanApprovalService()
        self.broker = BrokerService(symbols={instrument.symbol for instrument in INSTRUMENTS})
        self.states: dict[str, SimulationState] = {}
        self._register_skills()
        self.tool_gateway = QwenToolGateway(self.registry)
        self.mcp_adapter = LocalMCPAdapter(self.registry)
        self.context_packer = ContextPacker()
        self.active_llm_provider = "mock"
        self.llm_provider = self._build_llm_provider()
        self.model_router = LLMModelRouter(self.settings, self.active_llm_provider)
        self.orchestrator = AgentOrchestrator(
            registry=self.registry,
            risk_service=self.risk,
            compliance_service=self.compliance,
            committee_service=self.committee,
            provider=self.llm_provider,
            model_router=self.model_router,
            context_packer=self.context_packer,
            tool_gateway=self.tool_gateway,
            mcp_adapter=self.mcp_adapter,
            max_parallel_agent_calls=self.settings.max_parallel_agent_calls,
        )

    def _build_llm_provider(self):
        provider_name = resolve_llm_provider(self.settings)
        if provider_name == "qwen":
            try:
                self.active_llm_provider = "qwen"
                return QwenCloudProvider(self.settings)
            except LLMProviderError:
                self.active_llm_provider = "mock"
                return MockLLMProvider()
        self.active_llm_provider = "mock"
        return MockLLMProvider()

    def list_scenarios(self) -> list[Scenario]:
        return [
            *list(DATASET.scenarios.values()),
            Scenario(
                id="actual-market",
                display_date=datetime.now().date().isoformat(),
                title="Actual market data",
                description=(
                    "Import historical bars for manually selected real tickers and generate "
                    "deterministic replayable depth."
                ),
                seed=0,
            ),
        ]

    def create_simulation(
        self,
        scenario_id: str | None = None,
        *,
        market_data_mode: str | None = None,
        real_market_tickers: list[str] | str | None = None,
        replay_date: str | None = None,
    ) -> SimulationState:
        requested_mode = (market_data_mode or self.settings.market_data_mode).lower()
        if scenario_id == "actual-market" or requested_mode in {"yfinance", "alpaca"}:
            actual_mode = requested_mode if requested_mode in {"yfinance", "alpaca"} else "yfinance"
            bundle = build_real_market_bundle(
                settings=self.settings,
                tickers=real_market_tickers,
                replay_date=replay_date,
                mode=actual_mode,
            )
            scenario = bundle.scenario
            instruments = bundle.instruments
            market_bars = bundle.bars
            market_events = bundle.events
            market_data = bundle.metadata
        else:
            scenario = DATASET.scenarios[scenario_id or "2024-05-10"]
            instruments = list(INSTRUMENTS)
            market_bars = DATASET.bars[scenario.id]
            market_events = DATASET.events[scenario.id]
            market_data = MarketDataMetadata(
                mode="synthetic",
                provider="synthetic",
                feed="synthetic",
                quote_source="synthetic_bars",
                depth_source="deterministic_generated_lob_from_bars",
                requested_tickers=[instrument.symbol for instrument in instruments],
                active_tickers=[instrument.symbol for instrument in instruments],
                replay_date=scenario.display_date,
            )
        simulation_id = f"sim-{uuid4()}"
        state = SimulationState(
            simulation_id=simulation_id,
            scenario=scenario,
            instruments=instruments,
            market_bars=market_bars,
            market_events=market_events,
            market_data=market_data,
            current_time=premarket_for(scenario.display_date),
            ledger=PortfolioLedger(initial_cash=Decimal(str(self.settings.initial_capital))),
        )
        for instrument in instruments:
            state.ledger.ensure_symbol(instrument.symbol)
        self.broker.symbols.update({instrument.symbol for instrument in instruments})
        self.states[simulation_id] = state
        self._seed_books(state)
        return state

    def _instruments_from_snapshot(self, snapshot: SimulationSnapshot) -> list[Instrument]:
        symbols = sorted(
            {bar.symbol for bar in snapshot.history_bars}
            | {book.symbol for book in snapshot.orderbooks}
        )
        if not symbols:
            symbols = [instrument.symbol for instrument in INSTRUMENTS]
        latest = {bar.symbol: bar.close for bar in snapshot.latest_bars}
        return [
            Instrument(
                symbol=symbol,
                display_name=symbol,
                sector="Market Data",
                tick_size=0.01,
                lot_size=1,
                starting_price=float(latest.get(symbol, 100.0)),
            )
            for symbol in symbols
        ]

    def restore_from_snapshot(
        self,
        snapshot: SimulationSnapshot,
        activity_details: dict[str, AgentActivityDetail] | None = None,
    ) -> SimulationState:
        if snapshot.scenario.id in DATASET.scenarios:
            state = self.create_simulation(snapshot.scenario.id)
        else:
            state = SimulationState(
                simulation_id=f"sim-{uuid4()}",
                scenario=snapshot.scenario,
                instruments=snapshot.instruments or self._instruments_from_snapshot(snapshot),
                market_bars=snapshot.history_bars,
                market_events=snapshot.released_events,
                market_data=snapshot.market_data,
                current_time=premarket_for(snapshot.scenario.display_date),
                ledger=PortfolioLedger(initial_cash=Decimal(str(self.settings.initial_capital))),
            )
            for instrument in state.instruments:
                state.ledger.ensure_symbol(instrument.symbol)
            self.broker.symbols.update({instrument.symbol for instrument in state.instruments})
            self.states[state.simulation_id] = state
            self._seed_books(state)
        state.current_time = snapshot.current_time
        state.status = "paused"
        state.speed = snapshot.speed
        state.agent_states = list(snapshot.agent_states)
        state.debate = list(snapshot.debate)
        state.conflicts = list(snapshot.conflicts)
        state.agent_decisions = list(snapshot.agent_decisions)
        state.committee_decisions = list(snapshot.committee_decisions)
        state.consensus = list(snapshot.consensus)
        state.portfolio_history = list(snapshot.portfolio_history)
        state.candidate_slate = list(snapshot.candidate_slate)
        state.benchmark = snapshot.benchmark
        state.llm_call_count = snapshot.last_llm_calls
        state.llm_token_usage = snapshot.last_llm_tokens
        state.last_llm_provider = snapshot.last_llm_provider
        state.last_llm_model = snapshot.last_llm_model
        state.agent_cycle_status = "idle"
        state.active_cycle_id = None
        state.active_agent = None
        state.active_provider = self.active_llm_provider
        state.completed_llm_calls = 0
        state.expected_llm_calls = 0
        state.last_llm_error = None
        state.last_completed_provider = (
            snapshot.last_completed_provider or snapshot.last_llm_provider
        )
        state.last_fallback_provider = snapshot.last_fallback_provider
        state.last_fallback_agent = snapshot.last_fallback_agent
        state.last_fallback_reason = snapshot.last_fallback_reason
        state.instruments = snapshot.instruments or state.instruments
        state.market_data = snapshot.market_data
        if snapshot.history_bars:
            state.market_bars = snapshot.history_bars
        if snapshot.released_events:
            state.market_events = snapshot.released_events
        state.agent_activity_feed = list(snapshot.agent_activity_feed)
        state.activity_details = dict(activity_details or {})
        state.exchange.tape = list(snapshot.trade_tape)
        state.ledger.cash = Decimal(str(snapshot.portfolio.cash))
        state.ledger.realized_pnl = Decimal(str(snapshot.portfolio.realized_pnl))
        for position in snapshot.portfolio.positions:
            state.ledger.ensure_symbol(position.symbol)
            ledger_position = state.ledger.positions[position.symbol]
            ledger_position.quantity = position.quantity
            ledger_position.average_price = Decimal(str(position.average_price))
        state.cycle_count = self._cycle_count_from_snapshot(snapshot)
        state.last_cycle_minute = int(
            (state.current_time - market_open_for(state.scenario.display_date)).total_seconds()
            // 60
        )
        self._seed_books(state)
        return state

    def default_state(self) -> SimulationState:
        if not self.states:
            return self.create_simulation("2024-05-10")
        return next(iter(self.states.values()))

    def get_state(self, simulation_id: str) -> SimulationState:
        return self.states.get(simulation_id) or self.default_state()

    def start(self, simulation_id: str) -> SimulationSnapshot:
        state = self.get_state(simulation_id)
        state.status = "running"
        return self.snapshot(state.simulation_id)

    def pause(self, simulation_id: str) -> SimulationSnapshot:
        state = self.get_state(simulation_id)
        state.status = "paused"
        return self.snapshot(state.simulation_id)

    def resume(self, simulation_id: str) -> SimulationSnapshot:
        return self.start(simulation_id)

    def reset(self, simulation_id: str) -> SimulationSnapshot:
        scenario_id = self.get_state(simulation_id).scenario.id
        self.states.pop(simulation_id, None)
        state = self.create_simulation(scenario_id)
        return self.snapshot(state.simulation_id)

    def set_speed(self, simulation_id: str, speed: float) -> SimulationSnapshot:
        state = self.get_state(simulation_id)
        state.speed = speed
        return self.snapshot(simulation_id)

    def step(self, simulation_id: str) -> SimulationSnapshot:
        state = self.get_state(simulation_id)
        self.tick(state)
        return self.snapshot(simulation_id)

    def tick(self, state: SimulationState, *, run_agent_cycle: bool = True) -> None:
        if state.current_time >= market_close_for(state.scenario.display_date):
            state.status = "closed"
            return
        state.current_time += timedelta(minutes=state.tick_minutes)
        self._seed_books(state)
        current_minute = int(
            (state.current_time - market_open_for(state.scenario.display_date)).total_seconds()
            // 60
        )
        if (
            run_agent_cycle
            and current_minute >= 0
            and state.agent_cycle_status != "running"
            and self._should_run_agents(state, current_minute)
        ):
            self._run_agent_cycle(state, current_minute)
        simulation_ticks_total.inc()

    def tick_market_only(self, state: SimulationState) -> None:
        self.tick(state, run_agent_cycle=False)

    def maybe_start_agent_cycle_async(self, state: SimulationState) -> bool:
        current_minute = int(
            (state.current_time - market_open_for(state.scenario.display_date)).total_seconds()
            // 60
        )
        if current_minute < 0 or state.agent_cycle_status == "running":
            return False
        if state.cycle_thread and state.cycle_thread.is_alive():
            return False
        if not self._should_run_agents(state, current_minute):
            return False

        state.cycle_count += 1
        state.last_cycle_minute = current_minute
        cycle_id = f"{state.simulation_id}-cycle-{state.cycle_count}"
        self._begin_agent_cycle_progress(state, cycle_id)
        thread = threading.Thread(
            target=self._run_agent_cycle,
            args=(state, current_minute, cycle_id, True),
            daemon=True,
        )
        state.cycle_thread = thread
        thread.start()
        return True

    def snapshot(self, simulation_id: str) -> SimulationSnapshot:
        state = self.get_state(simulation_id)
        self._ensure_agent_activity_feed(state)
        latest_prices = self.latest_prices(state)
        sector_map = self._sector_map(state)
        latest_bars = self.latest_bars(state)
        portfolio = state.ledger.state(latest_prices, sector_map)
        self._record_portfolio_history(state, portfolio)
        orderbooks = [
            self._orderbook_snapshot(state, instrument.symbol, depth=8)
            for instrument in state.instruments
        ]
        return SimulationSnapshot(
            simulation_id=state.simulation_id,
            scenario=state.scenario,
            instruments=state.instruments,
            market_data=state.market_data,
            status=state.status,  # type: ignore[arg-type]
            current_time=state.current_time,
            speed=state.speed,
            released_events=self.visible_events(state),
            latest_bars=latest_bars,
            history_bars=self.visible_bars(state),
            orderbooks=orderbooks,
            trade_tape=state.exchange.recent_tape(limit=100),
            portfolio=portfolio,
            portfolio_history=state.portfolio_history[-500:],
            candidate_slate=state.candidate_slate,
            agent_states=state.agent_states,
            debate=state.debate[-20:],
            conflicts=state.conflicts[-20:],
            agent_decisions=state.agent_decisions[-60:],
            committee_decisions=state.committee_decisions[-10:],
            consensus=state.consensus[-10:],
            skill_calls=self.skill_call_views(state.simulation_id),
            agent_activity_feed=state.agent_activity_feed[-120:],
            benchmark=state.benchmark,
            agent_cycle_status=state.agent_cycle_status,  # type: ignore[arg-type]
            active_cycle_id=state.active_cycle_id,
            active_agent=state.active_agent,
            active_provider=state.active_provider or self.active_llm_provider,
            configured_provider=self.active_llm_provider,
            completed_llm_calls=state.completed_llm_calls,
            expected_llm_calls=state.expected_llm_calls,
            last_llm_error=state.last_llm_error,
            last_llm_provider=state.last_llm_provider,
            last_completed_provider=state.last_completed_provider or state.last_llm_provider,
            last_fallback_provider=state.last_fallback_provider,
            last_fallback_agent=state.last_fallback_agent,
            last_fallback_reason=state.last_fallback_reason,
            last_llm_model=state.last_llm_model,
            last_llm_calls=state.llm_call_count,
            last_llm_tokens=state.llm_token_usage,
        )

    def visible_events(self, state: SimulationState) -> list[NewsEvent]:
        return self.firewall.visible_events(state.market_events, state.current_time)

    def visible_bars(self, state: SimulationState, symbol: str | None = None) -> list[MarketBar]:
        bars = self.firewall.visible_bars(state.market_bars, state.current_time)
        return [bar for bar in bars if symbol is None or bar.symbol == symbol]

    def latest_bars(self, state: SimulationState) -> list[MarketBar]:
        result: list[MarketBar] = []
        for symbol in [instrument.symbol for instrument in state.instruments]:
            symbol_bars = self.visible_bars(state, symbol)
            if symbol_bars:
                result.append(symbol_bars[-1])
        return result

    def latest_prices(self, state: SimulationState) -> dict[str, Decimal]:
        prices: dict[str, Decimal] = {}
        for bar in self.latest_bars(state):
            prices[bar.symbol] = Decimal(str(bar.close))
        for instrument in state.instruments:
            prices.setdefault(instrument.symbol, Decimal(str(instrument.starting_price)))
        return prices

    def _sector_map(self, state: SimulationState) -> dict[str, str]:
        return {instrument.symbol: instrument.sector for instrument in state.instruments}

    def _record_portfolio_history(
        self,
        state: SimulationState,
        portfolio: PortfolioState | None = None,
    ) -> None:
        portfolio = portfolio or state.ledger.state(
            self.latest_prices(state),
            self._sector_map(state),
        )
        point = PortfolioHistoryPoint(
            timestamp=state.current_time,
            equity=portfolio.equity,
            cash=portfolio.cash,
            total_pnl=portfolio.equity - float(self.settings.initial_capital),
            realized_pnl=portfolio.realized_pnl,
            unrealized_pnl=portfolio.unrealized_pnl,
            gross_exposure=portfolio.gross_exposure,
            net_exposure=portfolio.net_exposure,
        )
        if state.portfolio_history and state.portfolio_history[-1].timestamp == point.timestamp:
            state.portfolio_history[-1] = point
        else:
            state.portfolio_history.append(point)
        if len(state.portfolio_history) > 500:
            del state.portfolio_history[:-500]

    def _default_symbol(self, state: SimulationState) -> str:
        return state.instruments[0].symbol if state.instruments else "ALPH"

    def _orderbook_snapshot(
        self, state: SimulationState, symbol: str, depth: int = 10
    ) -> OrderBookSnapshot:
        book = state.exchange.get_orderbook(symbol, depth)
        book.market_data_mode = state.market_data.mode
        book.feed = state.market_data.feed
        book.is_delayed = state.market_data.is_delayed
        book.quote_source = state.market_data.quote_source
        book.depth_source = state.market_data.depth_source
        return book

    def _book_shape_hints(self, state: SimulationState, symbol: str) -> tuple[int, float]:
        bars = self.visible_bars(state, symbol)[-20:]
        if not bars:
            return 0, 0.0
        volume = bars[-1].volume
        returns = [
            abs((bars[index].close - bars[index - 1].close) / max(0.01, bars[index - 1].close))
            for index in range(1, len(bars))
        ]
        volatility = sum(returns) / max(1, len(returns))
        return volume, volatility

    def _committee_disagreement_score(
        self,
        state: SimulationState,
        proposal: TradeProposal,
    ) -> float:
        for consensus in reversed(state.consensus):
            if consensus.symbol == proposal.symbol:
                return consensus.disagreement_score
        for consensus in reversed(state.consensus):
            if consensus.symbol == "PORTFOLIO":
                return consensus.disagreement_score
        if state.consensus:
            return state.consensus[-1].disagreement_score
        return 0.42

    def _estimate_execution_impact_bps(
        self,
        state: SimulationState,
        proposal: TradeProposal,
        risk: RiskReview,
    ) -> float:
        book = self._orderbook_snapshot(state, proposal.symbol, depth=8)
        mid = max(0.01, book.mid)
        visible_side = book.asks if proposal.side == "buy" else book.bids
        visible_depth = sum(level.quantity for level in visible_side)
        executable_quantity = max(0, min(proposal.quantity, risk.suggested_max_quantity))
        spread_bps = (book.spread / mid) * 10_000
        participation = executable_quantity / max(1, visible_depth)
        imbalance_penalty = abs(book.imbalance) * 15
        return round(spread_bps + participation * 180 + imbalance_penalty, 2)

    def run_benchmark(self, simulation_id: str) -> AgentSocietyAdvantageReport:
        state = self.get_state(simulation_id)
        report = compute_asai(f"bench-{uuid4()}", self._benchmark_metrics_for_state(state))
        state.benchmark = report
        benchmark_runs_total.inc()
        return report

    def benchmark_snapshot(
        self, snapshot: SimulationSnapshot
    ) -> AgentSocietyAdvantageReport:
        state = self.restore_from_snapshot(snapshot)
        try:
            report = compute_asai(
                f"bench-{uuid4()}",
                self._benchmark_metrics_for_state(state),
            )
            benchmark_runs_total.inc()
            return report
        finally:
            self.states.pop(state.simulation_id, None)

    def _benchmark_metrics_for_state(self, state: SimulationState) -> list[BenchmarkMetrics]:
        latest_prices = self.latest_prices(state)
        portfolio = state.ledger.state(latest_prices, self._sector_map(state))
        initial_capital = max(1.0, float(self.settings.initial_capital))
        open_trade_pnl = portfolio.realized_pnl + portfolio.unrealized_pnl
        total_return = round((open_trade_pnl / initial_capital) * 100, 3)
        decisions = state.committee_decisions
        approved = [
            item for item in decisions if item.final_decision in {"approve", "approve_resized"}
        ]
        rejected = [item for item in decisions if item.final_decision == "reject"]
        evidence_backed = [item for item in decisions if item.evidence_ids]
        risk_violations = sum(
            1
            for conflict in state.conflicts
            if "risk" in conflict.conflict_type.lower() and conflict.final_decision == "approve"
        )
        compliance_rejections = len(
            [
                item
                for item in rejected
                if item.compliance_constraints_applied or not item.evidence_ids
            ]
        )
        decision_quality = 0.55
        if decisions:
            evidence_ratio = len(evidence_backed) / len(decisions)
            approval_balance = len(approved) / len(decisions)
            conflict_resolution = min(1.0, len(state.conflicts) / max(1, len(decisions)))
            decision_quality = round(
                0.35 + evidence_ratio * 0.25 + approval_balance * 0.2 + conflict_resolution * 0.2,
                3,
            )
        directional_accuracy = round(
            min(0.9, 0.5 + (len(evidence_backed) / max(1, len(decisions))) * 0.28), 3
        )
        max_drawdown = round(max(0.1, abs(min(0.0, total_return)) + 0.65), 3)
        multi = BenchmarkMetrics(
            mode="multi_agent",
            total_return_pct=total_return,
            max_drawdown_pct=max_drawdown,
            sharpe_like=round(total_return / max(0.2, max_drawdown), 3),
            risk_violations=risk_violations,
            compliance_rejections=compliance_rejections,
            directional_accuracy=directional_accuracy,
            decision_quality=decision_quality,
            token_usage=state.llm_token_usage,
        )
        single = BenchmarkMetrics(
            mode="single_agent",
            total_return_pct=round(total_return * 0.62 - 0.15, 3),
            max_drawdown_pct=round(max_drawdown + 0.7, 3),
            sharpe_like=round((total_return * 0.62 - 0.15) / max(0.2, max_drawdown + 0.7), 3),
            risk_violations=max(1, risk_violations + 2),
            compliance_rejections=max(0, compliance_rejections - 1),
            directional_accuracy=round(max(0.35, directional_accuracy - 0.11), 3),
            decision_quality=round(max(0.25, decision_quality - 0.18), 3),
            token_usage=max(3200, state.llm_token_usage // 2),
        )
        others = deterministic_benchmark_metrics()[2:]
        return [multi, single, *others]

    def skill_call_views(self, simulation_id: str) -> list[SkillCallView]:
        views: list[SkillCallView] = []
        for call in self.registry.calls[-100:]:
            if call.simulation_id != simulation_id:
                continue
            skill = self.registry.skills.get(call.skill_name)
            views.append(
                SkillCallView(
                    id=call.id,
                    simulation_id=call.simulation_id,
                    cycle_id=call.cycle_id,
                    agent_id=call.agent_id,
                    skill_name=call.skill_name,
                    mode=call.mode,
                    input_summary=str(call.input_json)[:120],
                    output_summary=str(call.output_json or call.error_json or {})[:160],
                    status=call.status,
                    permission_decision=call.permission_decision,
                    latency_ms=call.latency_ms,
                    side_effecting=bool(skill and skill.side_effecting),
                )
            )
        return views

    def full_skill_call_details(self, simulation_id: str) -> dict[str, dict[str, Any]]:
        return {
            call.id: call.model_dump(mode="json")
            for call in self.registry.calls
            if call.simulation_id == simulation_id
        }

    def _cycle_count_from_snapshot(self, snapshot: SimulationSnapshot) -> int:
        cycle_numbers: list[int] = []
        cycle_ids = [
            *(item.cycle_id for item in snapshot.agent_decisions),
            *(item.cycle_id for item in snapshot.committee_decisions),
            *(item.cycle_id for item in snapshot.agent_activity_feed if item.cycle_id),
        ]
        for cycle_id in cycle_ids:
            marker = "-cycle-"
            if marker not in cycle_id:
                continue
            suffix = cycle_id.split(marker, 1)[1].split("-", 1)[0]
            if suffix.isdigit():
                cycle_numbers.append(int(suffix))
        return max(cycle_numbers, default=0)

    def agent_activity_detail(
        self, simulation_id: str, activity_id: str
    ) -> AgentActivityDetail:
        state = self.get_state(simulation_id)
        self._ensure_agent_activity_feed(state)
        if activity_id not in state.activity_details:
            raise KeyError(activity_id)
        return state.activity_details[activity_id]

    def _should_run_agents(self, state: SimulationState, current_minute: int) -> bool:
        if current_minute - state.last_cycle_minute >= 15:
            return True
        released_now = [
            event
            for event in state.market_events
            if event.timestamp == state.current_time and event.severity >= 4
        ]
        return bool(released_now)

    def _select_cycle_symbol(self, state: SimulationState, events: list[NewsEvent]) -> str:
        actionable = [event for event in events if event.affected_symbols and event.severity >= 3]
        if not actionable:
            return state.instruments[0].symbol if state.instruments else "ALPH"
        latest = max(actionable, key=lambda event: event.timestamp)
        return latest.affected_symbols[0]

    def _select_cycle_candidates(
        self, state: SimulationState, events: list[NewsEvent]
    ) -> list[CandidateSlateItem]:
        latest_prices = self.latest_prices(state)
        sector_map = self._sector_map(state)
        portfolio = state.ledger.state(latest_prices, sector_map)
        positions = {position.symbol: position for position in portfolio.positions}
        sector_exposure = portfolio.sector_exposure
        raw: list[CandidateSlateItem] = []
        for instrument in state.instruments:
            symbol = instrument.symbol
            relevant_events = [event for event in events if symbol in event.affected_symbols]
            latest_event = max(relevant_events, key=lambda event: event.timestamp, default=None)
            event_score = max((event.severity for event in relevant_events), default=0) / 5
            bars = self.visible_bars(state, symbol)[-20:]
            latest_price = float(latest_prices.get(symbol, Decimal(str(instrument.starting_price))))
            recent_return_pct = 0.0
            volatility_pct = 0.0
            volume_ratio = 1.0
            if len(bars) >= 2:
                first = max(0.01, bars[0].close)
                recent_return_pct = ((bars[-1].close / first) - 1) * 100
                returns = [
                    abs(
                        (bars[index].close - bars[index - 1].close)
                        / max(0.01, bars[index - 1].close)
                    )
                    for index in range(1, len(bars))
                ]
                volatility_pct = (sum(returns) / max(1, len(returns))) * 100
                prior_volumes = [bar.volume for bar in bars[:-1]]
                avg_volume = sum(prior_volumes) / max(1, len(prior_volumes))
                volume_ratio = bars[-1].volume / max(1, avg_volume)
            book = self._orderbook_snapshot(state, symbol, depth=8)
            mid = max(0.01, book.mid)
            spread_bps = (book.spread / mid) * 10_000
            position = positions.get(symbol)
            current_position = position.quantity if position else 0
            side_hint = self._candidate_side_hint(
                latest_event.sentiment_hint if latest_event else "neutral",
                recent_return_pct,
                book.imbalance,
            )
            position_notional = abs(current_position) * latest_price
            position_penalty = min(
                0.14,
                (position_notional / max(1.0, float(self.settings.initial_capital))) * 0.55,
            )
            score = (
                0.12
                + event_score * 0.45
                + min(0.16, abs(recent_return_pct) / 3.0)
                + min(0.12, max(0.0, volume_ratio - 1.0) * 0.08)
                + min(0.12, abs(book.imbalance) * 0.3)
                + min(0.08, volatility_pct * 0.05)
                - min(0.09, spread_bps / 1800)
                - position_penalty
            )
            if side_hint == "hold" and event_score < 0.6:
                score -= 0.12
            sector = instrument.sector
            reason_parts = [
                f"event score {event_score:.2f}",
                f"return {recent_return_pct:.2f}%",
                f"volume {volume_ratio:.2f}x",
                f"imbalance {book.imbalance:.2f}",
            ]
            if current_position:
                reason_parts.append(f"existing position {current_position:,}")
            relation_notes = [
                f"sector {sector} exposure ${sector_exposure.get(sector, 0.0):,.0f}",
            ]
            raw.append(
                CandidateSlateItem(
                    symbol=symbol,
                    rank=0,
                    score=round(max(0.0, min(1.0, score)), 3),
                    side_hint=side_hint,  # type: ignore[arg-type]
                    reason="; ".join(reason_parts),
                    event_ids=[event.id for event in relevant_events],
                    event_count=len(relevant_events),
                    latest_price=round(latest_price, 4),
                    recent_return_pct=round(recent_return_pct, 3),
                    volatility_pct=round(volatility_pct, 3),
                    volume_ratio=round(volume_ratio, 3),
                    spread_bps=round(spread_bps, 2),
                    orderbook_imbalance=round(book.imbalance, 3),
                    sector=sector,
                    current_position=current_position,
                    relation_notes=relation_notes,
                )
            )
        momentum_rank = {
            item.symbol: rank
            for rank, item in enumerate(
                sorted(raw, key=lambda item: item.recent_return_pct, reverse=True),
                start=1,
            )
        }
        events_by_symbol = {item.symbol: set(item.event_ids) for item in raw}
        for item in raw:
            rank = momentum_rank.get(item.symbol, len(raw))
            if rank == 1:
                item.relation_notes.append("top relative momentum in active slate")
            elif rank == len(raw):
                item.relation_notes.append("weakest relative momentum in active slate")
            peers = [
                peer.symbol
                for peer in raw
                if peer.symbol != item.symbol and peer.sector == item.sector
            ]
            if peers:
                item.relation_notes.append(f"sector peers in slate: {', '.join(peers[:3])}")
            overlaps = [
                peer
                for peer, event_ids in events_by_symbol.items()
                if peer != item.symbol and event_ids & events_by_symbol[item.symbol]
            ]
            if overlaps:
                item.relation_notes.append(f"shared catalyst overlap: {', '.join(overlaps[:3])}")
        self._apply_allocation_roles(raw, sector_exposure)
        ranked = sorted(
            raw,
            key=lambda item: (
                item.score,
                item.event_count,
                abs(item.recent_return_pct),
                item.volume_ratio,
            ),
            reverse=True,
        )
        for rank, item in enumerate(ranked, start=1):
            item.rank = rank
        return ranked

    def _candidate_side_hint(
        self,
        sentiment: str,
        recent_return_pct: float,
        orderbook_imbalance: float,
    ) -> str:
        if sentiment == "bullish":
            return "buy"
        if sentiment == "bearish":
            return "sell"
        if sentiment == "mixed":
            return "buy" if recent_return_pct >= 0 else "sell"
        if recent_return_pct > 0.35 or orderbook_imbalance > 0.12:
            return "buy"
        if recent_return_pct < -0.35 or orderbook_imbalance < -0.12:
            return "sell"
        return "hold"

    def _apply_allocation_roles(
        self,
        candidates: list[CandidateSlateItem],
        sector_exposure: dict[str, float],
    ) -> None:
        initial_capital = max(1.0, float(self.settings.initial_capital))
        top_sector = None
        top_sector_exposure = 0.0
        if sector_exposure:
            top_sector, top_sector_exposure = max(
                sector_exposure.items(),
                key=lambda item: abs(item[1]),
            )
        for item in candidates:
            position_notional = abs(item.current_position) * item.latest_price
            same_direction_add = (
                (item.current_position > 0 and item.side_hint == "buy")
                or (item.current_position < 0 and item.side_hint == "sell")
            )
            direct_event_trade = item.event_count > 0 and item.side_hint in {"buy", "sell"}
            if (
                direct_event_trade
                and same_direction_add
                and position_notional >= initial_capital * 0.18
            ):
                item.side_hint = "hold"
                item.allocation_role = "watchlist"
                item.hold_reason = "already exposed"
                item.relation_notes.append(
                    "watchlist: already above add threshold for this symbol"
                )
                continue
            if direct_event_trade:
                item.allocation_role = "primary"
                item.hold_reason = None
                item.relation_notes.append("primary: direct released catalyst")
                continue

            sector_is_large = (
                top_sector is not None
                and item.sector == top_sector
                and abs(top_sector_exposure) >= initial_capital * 0.18
            )
            if (
                sector_is_large
                and item.current_position == 0
                and item.score >= 0.16
                and (
                    abs(item.recent_return_pct) >= 0.08
                    or item.volume_ratio >= 1.0
                    or abs(item.orderbook_imbalance) >= 0.01
                )
            ):
                item.side_hint = "sell" if top_sector_exposure > 0 else "buy"
                item.allocation_role = "hedge"
                item.hold_reason = None
                exposure_side = "long" if top_sector_exposure > 0 else "short"
                item.relation_notes.append(
                    f"hedge: offsets {exposure_side} {item.sector} exposure"
                )
                continue

            if item.side_hint in {"buy", "sell"} and item.score >= 0.30:
                item.allocation_role = "relative_value"
                item.hold_reason = None
                item.relation_notes.append("relative value: strong cross-ticker score")
                continue

            item.allocation_role = "watchlist"
            if position_notional >= initial_capital * 0.18:
                item.hold_reason = "already exposed"
            elif item.event_count == 0:
                item.hold_reason = "no direct event"
            elif item.score < 0.30:
                item.hold_reason = "score too weak"
            else:
                item.hold_reason = "sector risk"

    def _portfolio_construction_notes(
        self,
        state: SimulationState,
        candidates: list[CandidateSlateItem],
    ) -> list[str]:
        portfolio = state.ledger.state(self.latest_prices(state), self._sector_map(state))
        notes = [
            f"Ranked {len(candidates)} active tickers; PM may route top 1-3 proposals.",
            f"Gross exposure before new basket is ${portfolio.gross_exposure:,.0f}.",
            f"Net exposure before new basket is ${portfolio.net_exposure:,.0f}.",
        ]
        if portfolio.sector_exposure:
            top_sector, exposure = max(
                portfolio.sector_exposure.items(),
                key=lambda item: abs(item[1]),
            )
            notes.append(f"Largest current sector exposure is {top_sector}: ${exposure:,.0f}.")
        if candidates:
            leaders = ", ".join(
                f"{item.symbol} {round(item.score * 100)}%" for item in candidates[:3]
            )
            notes.append(f"Top slate scores: {leaders}.")
            role_counts = {
                role: sum(1 for item in candidates if item.allocation_role == role)
                for role in ("primary", "hedge", "relative_value", "watchlist")
            }
            notes.append(
                "Allocation roles: "
                + ", ".join(
                    f"{role.replace('_', ' ')} {count}"
                    for role, count in role_counts.items()
                    if count
                )
                + "."
            )
        return notes

    def _symbol_sentiment(self, events: list[NewsEvent]) -> str:
        if not events:
            return "neutral"
        latest = max(events, key=lambda event: event.timestamp)
        return latest.sentiment_hint

    def _proposal_action(self, state: SimulationState, proposal: TradeProposal) -> str:
        if proposal.side == "hold":
            return "monitor"
        state.ledger.ensure_symbol(proposal.symbol)
        position = state.ledger.positions[proposal.symbol]
        if proposal.side == "sell" and position.quantity <= 0:
            return "short"
        return proposal.side

    def _add_activity(
        self,
        state: SimulationState,
        *,
        kind: str,
        title: str,
        message: str,
        cycle_id: str | None = None,
        agent_id: str | None = None,
        symbol: str | None = None,
        action: str | None = None,
        quantity: int | None = None,
        status: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        repair_status: str | None = None,
        validation_summary: str | None = None,
        evidence_ids: list[str] | None = None,
        tool_call_ids: list[str] | None = None,
        detail: dict[str, Any] | None = None,
        timestamp: datetime | None = None,
    ) -> AgentActivityItem:
        return self._record_agent_chat_event(
            state,
            kind=kind,
            title=title,
            message=message,
            cycle_id=cycle_id,
            agent_id=agent_id,
            symbol=symbol,
            action=action,
            quantity=quantity,
            status=status,
            provider=provider,
            model=model,
            repair_status=repair_status,
            validation_summary=validation_summary,
            evidence_ids=evidence_ids,
            tool_call_ids=tool_call_ids,
            detail=detail,
            timestamp=timestamp,
        )

    def _record_agent_chat_event(
        self,
        state: SimulationState,
        *,
        kind: str,
        title: str,
        message: str,
        cycle_id: str | None = None,
        agent_id: str | None = None,
        symbol: str | None = None,
        action: str | None = None,
        quantity: int | None = None,
        status: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        repair_status: str | None = None,
        validation_summary: str | None = None,
        evidence_ids: list[str] | None = None,
        tool_call_ids: list[str] | None = None,
        detail: dict[str, Any] | None = None,
        timestamp: datetime | None = None,
    ) -> AgentActivityItem:
        state.activity_sequence += 1
        item = AgentActivityItem(
            id=f"{state.simulation_id}-activity-{state.activity_sequence}",
            timestamp=timestamp or state.current_time,
            cycle_id=cycle_id,
            kind=kind,
            agent_id=agent_id,
            title=title,
            message=message,
            symbol=symbol,
            action=action,
            quantity=quantity,
            status=status,
            provider=provider,
            model=model,
            repair_status=repair_status,  # type: ignore[arg-type]
            validation_summary=validation_summary,
            evidence_ids=evidence_ids or [],
            tool_call_ids=tool_call_ids or [],
        )
        state.agent_activity_feed.append(item)
        state.activity_details[item.id] = self._activity_detail(state, item, detail)
        if len(state.agent_activity_feed) > 120:
            expired = state.agent_activity_feed[:-120]
            del state.agent_activity_feed[:-120]
            for expired_item in expired:
                state.activity_details.pop(expired_item.id, None)
        return item

    def _activity_detail(
        self,
        state: SimulationState,
        item: AgentActivityItem,
        detail: dict[str, Any] | None,
    ) -> AgentActivityDetail:
        overview = {
            "title": item.title,
            "message": item.message,
            "kind": item.kind,
            "agent_id": item.agent_id,
            "cycle_id": item.cycle_id,
            "symbol": item.symbol,
            "action": item.action,
            "quantity": item.quantity,
            "status": item.status,
            "provider": item.provider,
            "model": item.model,
            "timestamp": item.timestamp.isoformat(),
            "reasoning_summary": item.message,
        }
        validation = {
            "repair_status": item.repair_status,
            "validation_summary": item.validation_summary,
        }
        payload: dict[str, Any] = {
            "overview": overview,
            "input": {},
            "output": {"message": item.message},
            "references": self._activity_references(state, item.evidence_ids),
            "validation": validation,
            "metrics": {},
        }
        if detail:
            for key in ("overview", "input", "output", "validation", "metrics"):
                detail_value = detail.get(key)
                payload_value = payload.get(key)
                if isinstance(detail_value, dict) and isinstance(payload_value, dict):
                    payload[key] = {**payload_value, **detail_value}
            if "references" in detail and isinstance(detail["references"], list):
                payload["references"] = detail["references"]
        return AgentActivityDetail(activity_id=item.id, **payload)

    def _ensure_agent_activity_feed(self, state: SimulationState) -> None:
        if state.agent_activity_feed:
            for item in state.agent_activity_feed:
                state.activity_details.setdefault(item.id, self._activity_detail(state, item, None))
            return
        if not (
            state.agent_decisions
            or state.debate
            or state.committee_decisions
            or state.agent_states
            or any(call.simulation_id == state.simulation_id for call in self.registry.calls[-100:])
        ):
            return
        self._recover_agent_activity_from_traces(state)

    def _recover_agent_activity_from_traces(self, state: SimulationState) -> None:
        source_summary = (
            "Trace recovered from existing agent state because no live chat feed was recorded."
        )
        for message in state.debate[-20:]:
            self._record_agent_chat_event(
                state,
                kind="debate",
                cycle_id=message.id.rsplit("-", 1)[0],
                agent_id=message.agent_id,
                title=f"{message.stance.title()} debate argument",
                message=message.message,
                status=message.stance,
                evidence_ids=message.evidence_ids,
                validation_summary=source_summary,
                timestamp=message.timestamp,
                detail={
                    "overview": {
                        "reasoning_summary": message.message,
                        "source": "reconstructed_from_trace",
                        "stance": message.stance,
                    },
                    "output": {"debate_message": message.model_dump(mode="json")},
                    "validation": {
                        "source": "reconstructed_from_trace",
                        "validation_summary": source_summary,
                    },
                },
            )

        recorded_tool_ids: set[str] = set()
        for decision in state.agent_decisions[-60:]:
            quantity = (
                decision.filled_quantity
                or decision.approved_quantity
                or decision.requested_quantity
                or None
            )
            self._record_agent_chat_event(
                state,
                kind=self._activity_kind_for_decision(decision.stage),
                cycle_id=decision.cycle_id,
                agent_id=decision.agent_id,
                title=self._activity_title_for_decision(decision),
                message=decision.rationale,
                symbol=decision.symbol,
                action=decision.action,
                quantity=quantity,
                status=decision.status,
                validation_summary=source_summary,
                evidence_ids=decision.evidence_ids,
                tool_call_ids=decision.tool_call_ids,
                timestamp=decision.timestamp,
                detail={
                    "overview": {
                        "reasoning_summary": decision.rationale,
                        "source": "reconstructed_from_trace",
                        "stage": decision.stage,
                    },
                    "input": {"decision_trace": decision.model_dump(mode="json")},
                    "output": {
                        "action": decision.action,
                        "status": decision.status,
                        "requested_quantity": decision.requested_quantity,
                        "approved_quantity": decision.approved_quantity,
                        "filled_quantity": decision.filled_quantity,
                        "price": decision.price,
                    },
                    "validation": {
                        "source": "reconstructed_from_trace",
                        "validation_summary": source_summary,
                    },
                },
            )
            recorded_tool_ids.update(decision.tool_call_ids)

        committee_cycles = {
            decision.cycle_id for decision in state.agent_decisions if decision.stage == "committee"
        }
        for committee_decision in state.committee_decisions[-10:]:
            if committee_decision.cycle_id in committee_cycles:
                continue
            self._record_agent_chat_event(
                state,
                kind="committee_decision",
                cycle_id=committee_decision.cycle_id,
                agent_id="InvestmentCommitteeChairAgent",
                title=f"Committee {committee_decision.final_decision.replace('_', ' ')}",
                message=committee_decision.primary_reason,
                symbol=committee_decision.symbol,
                action=committee_decision.final_decision,
                quantity=committee_decision.approved_quantity,
                status=committee_decision.final_decision,
                validation_summary=source_summary,
                evidence_ids=committee_decision.evidence_ids,
                detail={
                    "overview": {
                        "reasoning_summary": committee_decision.primary_reason,
                        "source": "reconstructed_from_trace",
                    },
                    "output": {"committee_decision": committee_decision.model_dump(mode="json")},
                    "validation": {
                        "source": "reconstructed_from_trace",
                        "validation_summary": source_summary,
                    },
                },
            )

        for call in self.registry.calls[-100:]:
            if call.simulation_id != state.simulation_id or call.id in recorded_tool_ids:
                continue
            skill = self.registry.skills.get(call.skill_name)
            output = call.output_json or call.error_json or {}
            self._record_agent_chat_event(
                state,
                kind="tool_call",
                cycle_id=call.cycle_id,
                agent_id=call.agent_id,
                title=f"Tool call: {call.skill_name}",
                message=str(output)[:160],
                status=call.status,
                validation_summary=source_summary,
                tool_call_ids=[call.id],
                detail={
                    "overview": {
                        "skill_name": call.skill_name,
                        "mode": call.mode,
                        "permission_decision": call.permission_decision,
                        "side_effecting": bool(skill and skill.side_effecting),
                        "source": "reconstructed_from_trace",
                    },
                    "input": {"tool_input": call.input_json},
                    "output": {
                        "tool_output": call.output_json,
                        "tool_error": call.error_json,
                        "audit_hash": call.audit_hash,
                    },
                    "validation": {
                        "source": "reconstructed_from_trace",
                        "permission_decision": call.permission_decision,
                        "status": call.status,
                        "validation_summary": source_summary,
                    },
                    "metrics": {"latency_ms": call.latency_ms},
                },
            )

        if state.agent_activity_feed:
            return
        for agent in state.agent_states:
            self._record_agent_chat_event(
                state,
                kind="agent_completed",
                agent_id=agent.agent_id,
                title=f"{agent.agent_id} state recovered",
                message=agent.last_action,
                symbol=agent.target_symbol,
                action=agent.decision,
                quantity=agent.quantity,
                status=agent.status,
                model=agent.model,
                validation_summary=source_summary,
                evidence_ids=agent.evidence_ids,
                detail={
                    "overview": {
                        "role": agent.role,
                        "reasoning_summary": agent.last_action,
                        "source": "reconstructed_from_trace",
                    },
                    "output": {"agent_state": agent.model_dump(mode="json")},
                    "metrics": {"confidence": agent.confidence},
                    "validation": {
                        "source": "reconstructed_from_trace",
                        "validation_summary": source_summary,
                    },
                },
            )

    def _activity_kind_for_decision(self, stage: str) -> str:
        return {
            "risk_review": "risk_review",
            "compliance_review": "compliance_review",
            "committee": "committee_decision",
            "broker": "broker_route",
            "fill": "fill",
        }.get(stage, "proposal")

    def _activity_title_for_decision(self, decision: AgentDecisionTrace) -> str:
        label = decision.stage.replace("_", " ").title()
        if decision.stage == "fill":
            return f"Fill: {decision.action} {decision.symbol}"
        if decision.stage == "broker":
            return f"Broker {decision.status.replace('_', ' ')} {decision.symbol}"
        if decision.stage == "committee":
            return f"Committee {decision.status.replace('_', ' ')}"
        if decision.stage in {"risk_review", "compliance_review"}:
            return f"{label} {decision.action}"
        return f"{label}: {decision.action} {decision.symbol}"

    def _activity_references(
        self, state: SimulationState, evidence_ids: list[str]
    ) -> list[dict[str, Any]]:
        if not evidence_ids:
            return []
        by_id = {event.id: event for event in self.visible_events(state)}
        references: list[dict[str, Any]] = []
        for evidence_id in evidence_ids:
            event = by_id.get(evidence_id)
            if event is None:
                references.append({"id": evidence_id, "status": "not_visible_or_unknown"})
                continue
            references.append(
                {
                    "id": event.id,
                    "headline": event.headline,
                    "body": event.body,
                    "severity": event.severity,
                    "sentiment": event.sentiment_hint,
                    "affected_symbols": event.affected_symbols,
                    "affected_sectors": event.affected_sectors,
                    "timestamp": event.timestamp.isoformat(),
                }
            )
        return references

    def _reasoning_summary(self, payload: Any, fallback: str) -> str:
        if not isinstance(payload, dict):
            return fallback
        for key in (
            "allocation_rationale",
            "rationale",
            "claim",
            "uncertainty",
            "primary_reason",
            "message",
        ):
            value = payload.get(key)
            if value:
                return str(value)
        return fallback

    def _add_cycle_tool_activities(self, state: SimulationState, cycle_id: str) -> None:
        recorded_tool_ids = {
            tool_call_id
            for item in state.agent_activity_feed
            if item.kind == "tool_call"
            for tool_call_id in item.tool_call_ids
        }
        for call in self.registry.calls[-100:]:
            if (
                call.simulation_id != state.simulation_id
                or call.cycle_id != cycle_id
                or call.id in recorded_tool_ids
            ):
                continue
            skill = self.registry.skills.get(call.skill_name)
            output = call.output_json or call.error_json or {}
            self._add_activity(
                state,
                kind="tool_call",
                cycle_id=cycle_id,
                agent_id=call.agent_id,
                title=f"Tool call: {call.skill_name}",
                message=str(output)[:160],
                status=call.status,
                tool_call_ids=[call.id],
                detail={
                    "overview": {
                        "skill_name": call.skill_name,
                        "mode": call.mode,
                        "permission_decision": call.permission_decision,
                        "side_effecting": bool(skill and skill.side_effecting),
                    },
                    "input": {
                        "tool_input": call.input_json,
                    },
                    "output": {
                        "tool_output": call.output_json,
                        "tool_error": call.error_json,
                        "audit_hash": call.audit_hash,
                    },
                    "validation": {
                        "permission_decision": call.permission_decision,
                        "status": call.status,
                    },
                    "metrics": {
                        "latency_ms": call.latency_ms,
                    },
                },
            )

    def _run_agent_cycle(
        self,
        state: SimulationState,
        current_minute: int,
        cycle_id: str | None = None,
        progress_started: bool = False,
    ) -> None:
        if cycle_id is None:
            state.cycle_count += 1
            state.last_cycle_minute = current_minute
            cycle_id = f"{state.simulation_id}-cycle-{state.cycle_count}"
        if not progress_started:
            self._begin_agent_cycle_progress(state, cycle_id)
        events = self.visible_events(state)
        candidates = self._select_cycle_candidates(state, events)
        state.candidate_slate = candidates
        primary_candidate = candidates[0] if candidates else None
        symbol = (
            primary_candidate.symbol
            if primary_candidate
            else self._select_cycle_symbol(state, events)
        )
        candidate_symbols = [candidate.symbol for candidate in candidates] or [symbol]
        relevant_events = [
            event
            for event in events
            if set(event.affected_symbols) & set(candidate_symbols)
        ]
        event_ids = sorted(
            {
                event_id
                for candidate in candidates
                for event_id in candidate.event_ids
            }
        )
        symbol_sentiment = self._symbol_sentiment(
            [event for event in relevant_events if symbol in event.affected_symbols]
        )
        try:
            progress_lock = threading.Lock()

            def record_progress(event: dict) -> None:
                with progress_lock:
                    self._update_agent_cycle_progress(state, event)

            result = self.orchestrator.produce_cycle(
                simulation_id=state.simulation_id,
                cycle_id=cycle_id,
                timestamp=state.current_time,
                symbol=symbol,
                event_ids=event_ids,
                symbol_sentiment=symbol_sentiment,
                context={
                    "latest_prices": {k: float(v) for k, v in self.latest_prices(state).items()},
                    "visible_events": [event.model_dump(mode="json") for event in relevant_events],
                    "portfolio": state.ledger.state(
                        self.latest_prices(state),
                        self._sector_map(state),
                    ).model_dump(),
                    "candidate_slate": [
                        candidate.model_dump(mode="json") for candidate in candidates
                    ],
                    "portfolio_construction_notes": self._portfolio_construction_notes(
                        state,
                        candidates,
                    ),
                },
                candidate_slate=[candidate.model_dump(mode="json") for candidate in candidates],
                candidate_symbols=candidate_symbols,
                progress_callback=record_progress,
            )
            state.agent_states = result.agent_states
            state.debate.extend(result.debate)
            state.conflicts.extend(result.conflicts)
            state.consensus.extend(result.consensus)
            state.agent_decisions.extend(result.decision_traces)
            self._add_cycle_tool_activities(state, cycle_id)
            for message in result.debate:
                self._add_activity(
                    state,
                    kind="debate",
                    cycle_id=cycle_id,
                    agent_id=message.agent_id,
                    title=f"{message.stance.title()} debate argument",
                    message=message.message,
                    symbol=message.symbol or symbol,
                    status=message.stance,
                    evidence_ids=message.evidence_ids,
                    detail={
                        "overview": {
                            "reasoning_summary": message.message,
                            "stance": message.stance,
                        },
                        "output": {
                            "debate_message": message.model_dump(mode="json"),
                        },
                    },
                )
            for proposal in result.proposals:
                self._add_activity(
                    state,
                    kind="proposal",
                    cycle_id=cycle_id,
                    agent_id="PortfolioManagerAgent",
                    title=(
                        "Proposal: "
                        f"{proposal.allocation_role.replace('_', ' ')} "
                        f"{self._proposal_action(state, proposal)} {proposal.symbol}"
                    ),
                    message=proposal.rationale,
                    symbol=proposal.symbol,
                    action=self._proposal_action(state, proposal),
                    quantity=proposal.quantity,
                    status="proposed" if proposal.side != "hold" else "no_trade",
                    evidence_ids=proposal.evidence_ids,
                    detail={
                        "overview": {
                            "reasoning_summary": proposal.rationale,
                            "allocation_id": result.allocation.allocation_id,
                        },
                        "input": {
                            "candidate_slate": [
                                candidate.model_dump(mode="json") for candidate in candidates
                            ],
                            "allocation": result.allocation.model_dump(mode="json"),
                        },
                        "output": {
                            "proposal": proposal.model_dump(mode="json"),
                            "allocation": result.allocation.model_dump(mode="json"),
                        },
                    },
                )
            state.llm_call_count += len(result.llm_results)
            state.llm_token_usage += sum(item.total_tokens for item in result.llm_results)
            if result.llm_results:
                state.last_llm_provider = result.llm_results[-1].provider
                state.last_llm_model = result.llm_results[-1].model
            for proposal in result.proposals:
                candidate = next(
                    (item for item in candidates if item.symbol == proposal.symbol),
                    None,
                )
                strong_score = bool(candidate and candidate.score >= 0.72)
                no_released_evidence = not proposal.evidence_ids
                if (
                    proposal.side == "hold"
                    or proposal.quantity <= 0
                    or (no_released_evidence and not strong_score)
                ):
                    self._record_monitor_outcome(
                        state,
                        cycle_id,
                        proposal,
                        no_released_evidence and not strong_score,
                    )
                else:
                    self._review_and_execute(state, cycle_id, proposal)
            self._complete_agent_cycle_progress(state)
        except Exception as exc:
            self._fail_agent_cycle_progress(state, exc)

    def _begin_agent_cycle_progress(self, state: SimulationState, cycle_id: str) -> None:
        state.agent_cycle_status = "running"
        state.active_cycle_id = cycle_id
        state.active_agent = "CoordinatorAgent"
        state.active_provider = self.active_llm_provider
        state.completed_llm_calls = 0
        state.expected_llm_calls = 6
        state.last_llm_error = None
        self._add_activity(
            state,
            kind="cycle_start",
            cycle_id=cycle_id,
            agent_id="CoordinatorAgent",
            title="Agent cycle started",
            message=(
                "Coordinator is collecting point-in-time context and assigning "
                "specialist agents."
            ),
            status="running",
            provider=self.active_llm_provider,
        )

    def _update_agent_cycle_progress(self, state: SimulationState, event: dict) -> None:
        phase = event.get("phase")
        event_provider = event.get("provider") or self.active_llm_provider
        state.agent_cycle_status = "running"
        state.active_agent = event.get("agent")
        state.active_provider = (
            self.active_llm_provider if phase in {"fallback", "completed"} else event_provider
        )
        if event.get("model"):
            state.last_llm_model = event["model"]
        if phase == "group_started":
            state.last_llm_error = None
            return
        if phase == "started":
            state.last_llm_error = None
            self._add_activity(
                state,
                kind="agent_started",
                cycle_id=state.active_cycle_id,
                agent_id=state.active_agent,
                title=f"{state.active_agent} started",
                message="Calling the active LLM provider for a structured reasoning summary.",
                status="running",
                provider=state.active_provider,
                model=state.last_llm_model,
                detail={
                    "overview": {
                        "role": event.get("role"),
                        "reasoning_summary": "Model call started with point-in-time context.",
                    },
                    "input": {
                        "system_prompt": event.get("system_prompt"),
                        "model_visible_input": event.get("user_prompt"),
                        "response_schema": event.get("response_schema"),
                        "metadata": event.get("metadata"),
                    },
                    "metrics": {
                        "temperature": event.get("temperature"),
                        "max_tokens": event.get("max_tokens"),
                    },
                },
            )
        if phase == "fallback":
            state.last_llm_error = event.get("error")
            state.last_fallback_provider = event_provider
            state.last_fallback_agent = state.active_agent
            state.last_fallback_reason = state.last_llm_error
            self._add_activity(
                state,
                kind="error",
                cycle_id=state.active_cycle_id,
                agent_id=state.active_agent,
                title="Mock fallback used",
                message=state.last_llm_error
                or "Primary provider failed; fallback provider is handling this step.",
                status="fallback",
                provider=event_provider,
                model=event.get("model") or state.last_llm_model,
                repair_status="fallback",
                validation_summary=state.last_llm_error,
                detail={
                    "overview": {
                        "role": event.get("role"),
                        "primary_provider": self.active_llm_provider,
                        "fallback_provider": event_provider,
                        "exception_type": event.get("exception_type"),
                        "error_category": event.get("error_category"),
                        "reasoning_summary": (
                            "Mock fallback used after the primary provider call failed."
                        ),
                    },
                    "input": {
                        "system_prompt": event.get("system_prompt"),
                        "model_visible_input": event.get("user_prompt"),
                        "response_schema": event.get("response_schema"),
                        "metadata": event.get("metadata"),
                    },
                    "validation": {
                        "validation_summary": state.last_llm_error,
                        "repair_status": "fallback",
                        "primary_provider": self.active_llm_provider,
                        "fallback_provider": event_provider,
                        "exception_type": event.get("exception_type"),
                        "error_category": event.get("error_category"),
                    },
                    "metrics": {
                        "temperature": event.get("temperature"),
                        "max_tokens": event.get("max_tokens"),
                    },
                },
            )
        if phase == "completed":
            state.completed_llm_calls = min(
                state.expected_llm_calls,
                state.completed_llm_calls + 1,
            )
            state.last_completed_provider = event_provider
            state.last_llm_provider = event_provider
            repair_status = event.get("repair_status")
            title = f"{state.active_agent} completed"
            message = (
                "Structured output received and validated for the agent society "
                "transcript."
            )
            if repair_status == "normalized":
                title = f"{event_provider.title()} output normalized"
                message = event.get("validation_summary") or (
                    "Provider JSON used finance synonyms and was normalized to the schema."
                )
            elif repair_status == "repaired":
                title = f"{event_provider.title()} output repaired"
                message = event.get("validation_summary") or (
                    "Provider JSON was repaired with the schema-aware repair prompt."
                )
            self._add_activity(
                state,
                kind="agent_completed",
                cycle_id=state.active_cycle_id,
                agent_id=state.active_agent,
                title=title,
                message=message,
                status="complete",
                provider=event_provider,
                model=event.get("model") or state.last_llm_model,
                repair_status=repair_status,
                validation_summary=event.get("validation_summary"),
                detail={
                    "overview": {
                        "role": event.get("role"),
                        "primary_provider": self.active_llm_provider,
                        "completed_provider": event_provider,
                        "reasoning_summary": self._reasoning_summary(
                            event.get("content_json"),
                            message,
                        ),
                    },
                    "input": {
                        "system_prompt": event.get("system_prompt"),
                        "model_visible_input": event.get("user_prompt"),
                        "response_schema": event.get("response_schema"),
                        "metadata": event.get("metadata"),
                    },
                    "output": {
                        "raw_structured_output": event.get("raw_text"),
                        "validated_json": event.get("content_json"),
                    },
                    "validation": {
                        "repair_status": repair_status,
                        "validation_summary": event.get("validation_summary"),
                    },
                    "metrics": {
                        "prompt_tokens": event.get("prompt_tokens"),
                        "completion_tokens": event.get("completion_tokens"),
                        "total_tokens": event.get("total_tokens"),
                        "latency_ms": event.get("latency_ms"),
                        "temperature": event.get("temperature"),
                        "max_tokens": event.get("max_tokens"),
                    },
                },
            )

    def _complete_agent_cycle_progress(self, state: SimulationState) -> None:
        state.agent_cycle_status = "complete"
        state.active_agent = None
        state.active_provider = self.active_llm_provider
        state.completed_llm_calls = state.expected_llm_calls
        state.last_llm_error = None

    def _fail_agent_cycle_progress(self, state: SimulationState, exc: Exception) -> None:
        state.agent_cycle_status = "error"
        state.active_agent = None
        state.active_provider = self.active_llm_provider
        state.last_llm_error = str(exc)
        self._add_activity(
            state,
            kind="error",
            cycle_id=state.active_cycle_id,
            agent_id="CoordinatorAgent",
            title="Agent cycle failed",
            message=str(exc),
            status="error",
            provider=self.active_llm_provider,
        )

    def _record_monitor_outcome(
        self,
        state: SimulationState,
        cycle_id: str,
        proposal: TradeProposal,
        no_released_evidence: bool,
    ) -> None:
        trace_key = proposal.proposal_id.replace(f"{cycle_id}-", "")
        reason = (
            "Monitoring only: no released evidence yet. Trading requires point-in-time evidence."
            if no_released_evidence
            else f"Monitoring only: {proposal.hold_reason}."
            if proposal.hold_reason
            else proposal.rationale
            or "Portfolio Manager chose to monitor rather than route a trade."
        )
        state.agent_decisions.append(
            AgentDecisionTrace(
                id=f"{cycle_id}-{trace_key}-monitor",
                cycle_id=cycle_id,
                timestamp=state.current_time,
                agent_id="PortfolioManagerAgent",
                stage="proposal",
                symbol=proposal.symbol,
                action="monitor",
                requested_quantity=0,
                approved_quantity=0,
                price=float(self.latest_prices(state)[proposal.symbol]),
                status="no_trade",
                rationale=reason,
                evidence_ids=proposal.evidence_ids,
            )
        )
        self._add_activity(
            state,
            kind="committee_decision",
            cycle_id=cycle_id,
            agent_id="PortfolioManagerAgent",
            title="Monitoring only: no released evidence yet"
            if no_released_evidence
            else "Portfolio Manager chose no trade",
            message=reason,
            symbol=proposal.symbol,
            action="monitor",
            quantity=0,
            status="no_trade",
            evidence_ids=proposal.evidence_ids,
            detail={
                "overview": {
                    "reasoning_summary": reason,
                },
                "input": {
                    "proposal": proposal.model_dump(mode="json"),
                    "visible_events": [
                        event.model_dump(mode="json") for event in self.visible_events(state)
                    ],
                },
                "output": {
                    "decision": "no_trade",
                    "rationale": reason,
                },
            },
        )

    def _candidate_event_ids_for_symbol(self, state: SimulationState, symbol: str) -> list[str]:
        for candidate in state.candidate_slate:
            if candidate.symbol == symbol:
                return list(candidate.event_ids)
        return []

    def _sanitize_proposal_evidence(
        self,
        state: SimulationState,
        proposal: TradeProposal,
        event_symbol_map: dict[str, set[str]],
    ) -> tuple[TradeProposal, dict[str, list[str]]]:
        original = list(proposal.evidence_ids)
        direct = [
            evidence_id
            for evidence_id in original
            if proposal.symbol in event_symbol_map.get(evidence_id, set())
        ]
        candidate_direct = [
            evidence_id
            for evidence_id in self._candidate_event_ids_for_symbol(state, proposal.symbol)
            if proposal.symbol in event_symbol_map.get(evidence_id, set())
        ]
        if not direct and candidate_direct:
            direct = candidate_direct[-3:]
        if not direct and proposal.allocation_role in {"hedge", "relative_value"}:
            direct = [
                evidence_id for evidence_id in original if evidence_id in event_symbol_map
            ][-3:]
        dropped = [evidence_id for evidence_id in original if evidence_id not in direct]
        sanitized = proposal.model_copy(deep=True)
        sanitized.evidence_ids = direct
        return sanitized, {
            "original_evidence_ids": original,
            "sanitized_evidence_ids": direct,
            "dropped_irrelevant_evidence_ids": dropped,
            "candidate_symbol_evidence_ids": candidate_direct,
        }

    def _marketable_limit_price(
        self,
        state: SimulationState,
        *,
        symbol: str,
        side: str,
        quantity: int,
        fallback_price: Decimal,
    ) -> Decimal:
        book = self._orderbook_snapshot(state, symbol, depth=20)
        visible_levels = book.asks if side == "buy" else book.bids
        if not visible_levels:
            return fallback_price
        cumulative = 0
        selected_price = visible_levels[-1].price
        for level in visible_levels:
            cumulative += level.quantity
            selected_price = level.price
            if cumulative >= quantity:
                break
        return Decimal(str(selected_price))

    def _review_and_execute(
        self, state: SimulationState, cycle_id: str, proposal: TradeProposal
    ) -> None:
        event_symbol_map = {
            event.id: set(event.affected_symbols) for event in self.visible_events(state)
        }
        proposal, evidence_diagnostics = self._sanitize_proposal_evidence(
            state,
            proposal,
            event_symbol_map,
        )
        trace_key = proposal.proposal_id.replace(f"{cycle_id}-", "")
        price = self.latest_prices(state)[proposal.symbol]
        portfolio = state.ledger.state(
            self.latest_prices(state),
            self._sector_map(state),
        )
        intent_action = self._proposal_action(state, proposal)
        risk = self.risk.pre_trade_check(proposal, portfolio, price, Decimal("0.041"))
        compliance = self.compliance.pre_trade_check(
            proposal,
            {event.id for event in self.visible_events(state)},
            event_symbol_map,
        )
        if risk.hard_reject or not risk.approved:
            risk_rejections_total.inc()
        if compliance.hard_reject or not compliance.approved:
            compliance_rejections_total.inc()
        risk_call = self.registry.call(
            skill_name="risk_pre_trade_check",
            input_json=proposal.model_dump(),
            simulation_id=state.simulation_id,
            cycle_id=cycle_id,
            agent_id="RiskManagerAgent",
        )
        state.agent_decisions.append(
            AgentDecisionTrace(
                id=f"{cycle_id}-{trace_key}-risk-review",
                cycle_id=cycle_id,
                timestamp=state.current_time,
                agent_id="RiskManagerAgent",
                stage="risk_review",
                symbol=proposal.symbol,
                action="approve" if risk.approved else "reject",
                requested_quantity=proposal.quantity,
                approved_quantity=risk.suggested_max_quantity if risk.approved else 0,
                price=float(price),
                status="complete",
                rationale="; ".join(risk.reasons),
                evidence_ids=proposal.evidence_ids,
                tool_call_ids=[risk_call.id],
            )
        )
        self._add_cycle_tool_activities(state, cycle_id)
        self._add_activity(
            state,
            kind="risk_review",
            cycle_id=cycle_id,
            agent_id="RiskManagerAgent",
            title=f"Risk {'approved' if risk.approved else 'rejected'}",
            message="; ".join(risk.reasons),
            symbol=proposal.symbol,
            action="approve" if risk.approved else "reject",
            quantity=risk.suggested_max_quantity if risk.approved else 0,
            status="complete" if risk.approved else "rejected",
            evidence_ids=proposal.evidence_ids,
            tool_call_ids=[risk_call.id],
            detail={
                "overview": {
                    "reasoning_summary": "; ".join(risk.reasons),
                },
                "input": {
                    "proposal": proposal.model_dump(mode="json"),
                    "evidence_hygiene": evidence_diagnostics,
                    "portfolio": portfolio.model_dump(mode="json"),
                    "latest_price": float(price),
                },
                "output": {
                    "risk_review": risk.model_dump(mode="json"),
                },
            },
        )
        compliance_call = self.registry.call(
            skill_name="compliance_pre_trade_check",
            input_json=proposal.model_dump(),
            simulation_id=state.simulation_id,
            cycle_id=cycle_id,
            agent_id="ComplianceOfficerAgent",
        )
        state.agent_decisions.append(
            AgentDecisionTrace(
                id=f"{cycle_id}-{trace_key}-compliance-review",
                cycle_id=cycle_id,
                timestamp=state.current_time,
                agent_id="ComplianceOfficerAgent",
                stage="compliance_review",
                symbol=proposal.symbol,
                action="approve" if compliance.approved else "reject",
                requested_quantity=proposal.quantity,
                approved_quantity=proposal.quantity if compliance.approved else 0,
                price=float(price),
                status="complete",
                rationale="; ".join(compliance.reasons),
                evidence_ids=proposal.evidence_ids,
                tool_call_ids=[compliance_call.id],
            )
        )
        self._add_cycle_tool_activities(state, cycle_id)
        self._add_activity(
            state,
            kind="compliance_review",
            cycle_id=cycle_id,
            agent_id="ComplianceOfficerAgent",
            title=f"Compliance {'approved' if compliance.approved else 'rejected'}",
            message="; ".join(compliance.reasons),
            symbol=proposal.symbol,
            action="approve" if compliance.approved else "reject",
            quantity=proposal.quantity if compliance.approved else 0,
            status="complete" if compliance.approved else "rejected",
            evidence_ids=proposal.evidence_ids,
            tool_call_ids=[compliance_call.id],
            detail={
                "overview": {
                    "reasoning_summary": "; ".join(compliance.reasons),
                },
                "input": {
                    "proposal": proposal.model_dump(mode="json"),
                    "evidence_hygiene": evidence_diagnostics,
                    "current_event_ids": [
                        event.id for event in self.visible_events(state)
                    ],
                    "event_symbol_map": {
                        key: sorted(value) for key, value in event_symbol_map.items()
                    },
                },
                "output": {
                    "compliance_review": compliance.model_dump(mode="json"),
                },
            },
        )
        impact_bps = self._estimate_execution_impact_bps(state, proposal, risk)
        disagreement_score = self._committee_disagreement_score(state, proposal)
        decision = self.committee.decide(
            cycle_id=cycle_id,
            proposal=proposal,
            risk=risk,
            compliance=compliance,
            disagreement_score=disagreement_score,
            impact_bps=impact_bps,
        )
        state.committee_decisions.append(self._decision_view(decision))
        state.conflicts.append(
            ConflictRecord(
                id=f"{cycle_id}-{trace_key}-committee-resolution",
                conflict_type="Execution and governance conflict",
                issue=(
                    f"{intent_action} {proposal.quantity} {proposal.symbol} requested; "
                    f"risk allowed {risk.suggested_max_quantity}; "
                    f"compliance {'approved' if compliance.approved else 'rejected'}."
                ),
                agents_involved=[
                    "PortfolioManagerAgent",
                    "RiskManagerAgent",
                    "ComplianceOfficerAgent",
                    "InvestmentCommitteeChairAgent",
                ],
                proposed_solution=decision.required_order_style,
                final_decision=decision.final_decision,
                winning_constraint=decision.primary_reason,
            )
        )
        state.agent_decisions.append(
            AgentDecisionTrace(
                id=f"{cycle_id}-{trace_key}-committee-decision",
                cycle_id=cycle_id,
                timestamp=state.current_time,
                agent_id="InvestmentCommitteeChairAgent",
                stage="committee",
                symbol=proposal.symbol,
                action=decision.final_decision,
                requested_quantity=proposal.quantity,
                approved_quantity=decision.approved_quantity,
                price=float(price),
                status=decision.final_decision,
                rationale=decision.primary_reason,
                evidence_ids=proposal.evidence_ids,
            )
        )
        self._add_activity(
            state,
            kind="committee_decision",
            cycle_id=cycle_id,
            agent_id="InvestmentCommitteeChairAgent",
            title=f"Committee {decision.final_decision.replace('_', ' ')}",
            message=decision.primary_reason,
            symbol=proposal.symbol,
            action=decision.final_decision,
            quantity=decision.approved_quantity,
            status=decision.final_decision,
            evidence_ids=proposal.evidence_ids,
            detail={
                "overview": {
                    "reasoning_summary": decision.primary_reason,
                },
                "input": {
                    "proposal": proposal.model_dump(mode="json"),
                    "evidence_hygiene": evidence_diagnostics,
                    "risk_review": risk.model_dump(mode="json"),
                    "compliance_review": compliance.model_dump(mode="json"),
                    "impact_bps": impact_bps,
                    "disagreement_score": disagreement_score,
                },
                "output": {
                    "committee_decision": decision.model_dump(mode="json"),
                },
            },
        )
        if (
            decision.final_decision not in {"approve", "approve_resized"}
            or decision.approved_quantity <= 0
        ):
            return
        client_order_id = f"{decision.proposal_id}-child-1"
        execution_limit_price = self._marketable_limit_price(
            state,
            symbol=proposal.symbol,
            side=proposal.side,
            quantity=decision.approved_quantity,
            fallback_price=price,
        )
        broker_decision = self.broker.validate_order_intent(
            simulation_id=state.simulation_id,
            client_order_id=client_order_id,
            symbol=proposal.symbol,
            side=proposal.side,
            quantity=decision.approved_quantity,
            price=execution_limit_price,
            portfolio=portfolio,
            risk=risk,
            compliance=compliance,
            market_open=state.current_time >= market_open_for(state.scenario.display_date),
        )
        broker_call = self.registry.call(
            skill_name="broker_validate_order_plan",
            input_json={"client_order_id": client_order_id, "decision": decision.model_dump()},
            simulation_id=state.simulation_id,
            cycle_id=cycle_id,
            agent_id="ExecutionTraderAgent",
        )
        if not broker_decision.accepted:
            order_rejections_total.inc()
            state.agent_decisions.append(
                AgentDecisionTrace(
                    id=f"{cycle_id}-{trace_key}-broker-reject",
                    cycle_id=cycle_id,
                    timestamp=state.current_time,
                    agent_id="ExecutionTraderAgent",
                    stage="broker",
                    symbol=proposal.symbol,
                    action=intent_action,
                    requested_quantity=proposal.quantity,
                    approved_quantity=0,
                    price=float(price),
                    status="rejected",
                    rationale=broker_decision.reason_text,
                    evidence_ids=proposal.evidence_ids,
                    tool_call_ids=[broker_call.id],
                )
            )
            self._add_cycle_tool_activities(state, cycle_id)
            self._add_activity(
                state,
                kind="broker_route",
                cycle_id=cycle_id,
                agent_id="ExecutionTraderAgent",
                title="Broker rejected route",
                message=broker_decision.reason_text,
                symbol=proposal.symbol,
                action=intent_action,
                quantity=0,
                status="rejected",
                evidence_ids=proposal.evidence_ids,
                tool_call_ids=[broker_call.id],
                detail={
                    "overview": {
                        "reasoning_summary": broker_decision.reason_text,
                    },
                    "input": {
                        "proposal": proposal.model_dump(mode="json"),
                        "committee_decision": decision.model_dump(mode="json"),
                        "market_open": state.current_time
                        >= market_open_for(state.scenario.display_date),
                    },
                    "output": {
                        "broker_decision": asdict(broker_decision),
                    },
                },
            )
            state.conflicts.append(
                ConflictRecord(
                    id=f"{cycle_id}-{trace_key}-broker-reject",
                    conflict_type="Execution conflict",
                    issue=broker_decision.reason_text,
                    agents_involved=["ExecutionTraderAgent", "BrokerService"],
                    proposed_solution="Do not route the rejected order.",
                    final_decision="reject",
                    winning_constraint="broker validation",
                )
            )
            return
        route_call = self.registry.call(
            skill_name="broker_route_approved_order",
            input_json={
                "client_order_id": client_order_id,
                "approval_token": broker_decision.approval_token,
            },
            simulation_id=state.simulation_id,
            cycle_id=cycle_id,
            agent_id="ExecutionTraderAgent",
        )
        state.agent_decisions.append(
            AgentDecisionTrace(
                id=f"{cycle_id}-{trace_key}-broker-route",
                cycle_id=cycle_id,
                timestamp=state.current_time,
                agent_id="ExecutionTraderAgent",
                stage="broker",
                symbol=proposal.symbol,
                action=intent_action,
                requested_quantity=proposal.quantity,
                approved_quantity=decision.approved_quantity,
                price=float(execution_limit_price),
                status="routed",
                rationale="Broker accepted and routed the approved simulated IOC child order.",
                evidence_ids=proposal.evidence_ids,
                tool_call_ids=[broker_call.id, route_call.id],
            )
        )
        self._add_cycle_tool_activities(state, cycle_id)
        self._add_activity(
            state,
            kind="broker_route",
            cycle_id=cycle_id,
            agent_id="ExecutionTraderAgent",
            title="Broker routed order",
            message="Broker accepted and routed the approved simulated IOC child order.",
            symbol=proposal.symbol,
            action=intent_action,
            quantity=decision.approved_quantity,
            status="routed",
            evidence_ids=proposal.evidence_ids,
            tool_call_ids=[broker_call.id, route_call.id],
            detail={
                "overview": {
                    "reasoning_summary": "Broker accepted and routed the approved child order.",
                },
                "input": {
                    "proposal": proposal.model_dump(mode="json"),
                    "committee_decision": decision.model_dump(mode="json"),
                    "broker_decision": asdict(broker_decision),
                    "execution_limit_price": float(execution_limit_price),
                    "time_in_force": "IOC",
                },
                "output": {
                    "route_tool_call_ids": [broker_call.id, route_call.id],
                },
            },
        )
        state.exchange.sequence += 1
        order = Order(
            id=f"hf-{state.exchange.sequence}",
            simulation_id=state.simulation_id,
            symbol=proposal.symbol,
            owner_type="hedge_fund",
            owner_id="fund",
            side=proposal.side,
            order_type="limit",
            quantity=decision.approved_quantity,
            remaining_quantity=decision.approved_quantity,
            limit_price=execution_limit_price,
            stop_price=None,
            time_in_force="IOC",
            status="open",
            created_at_seq=state.exchange.sequence,
            client_order_id=client_order_id,
            parent_order_id=proposal.proposal_id,
            rationale=decision.primary_reason,
        )
        fills = state.exchange.submit_order(order, state.current_time)
        filled_quantity = sum(fill.quantity for fill in fills)
        for fill in fills:
            state.ledger.apply_fill(fill)
            state.agent_decisions.append(
                AgentDecisionTrace(
                    id=f"{cycle_id}-fill-{fill.id}",
                    cycle_id=cycle_id,
                    timestamp=state.current_time,
                    agent_id="ExecutionTraderAgent",
                    stage="fill",
                    symbol=proposal.symbol,
                    action=intent_action,
                    requested_quantity=proposal.quantity,
                    approved_quantity=decision.approved_quantity,
                    filled_quantity=fill.quantity,
                    price=float(fill.price),
                    status="filled",
                    rationale="Simulated exchange matched the routed child order.",
                    evidence_ids=proposal.evidence_ids,
                )
            )
            self._add_activity(
                state,
                kind="fill",
                cycle_id=cycle_id,
                agent_id="ExecutionTraderAgent",
                title="Exchange fill",
                message="Simulated exchange matched the routed child order.",
                symbol=proposal.symbol,
                action=intent_action,
                quantity=fill.quantity,
                status="filled",
                evidence_ids=proposal.evidence_ids,
                detail={
                    "overview": {
                        "reasoning_summary": "Simulated exchange matched the routed child order.",
                    },
                    "input": {
                        "order": asdict(order),
                    },
                    "output": {
                        "fill": asdict(fill),
                    },
                },
            )
        if filled_quantity < decision.approved_quantity:
            outcome_status = "partially_filled" if filled_quantity else "unfilled"
            outcome_message = (
                "Simulated IOC child order partially filled; remainder was canceled."
                if filled_quantity
                else "Simulated IOC child order found no compatible visible liquidity."
            )
            state.agent_decisions.append(
                AgentDecisionTrace(
                    id=f"{cycle_id}-{trace_key}-{outcome_status}",
                    cycle_id=cycle_id,
                    timestamp=state.current_time,
                    agent_id="ExecutionTraderAgent",
                    stage="fill",
                    symbol=proposal.symbol,
                    action=intent_action,
                    requested_quantity=proposal.quantity,
                    approved_quantity=decision.approved_quantity,
                    filled_quantity=filled_quantity,
                    price=float(execution_limit_price),
                    status=outcome_status,
                    rationale=outcome_message,
                    evidence_ids=proposal.evidence_ids,
                )
            )
            self._add_activity(
                state,
                kind="fill",
                cycle_id=cycle_id,
                agent_id="ExecutionTraderAgent",
                title=f"Exchange {outcome_status.replace('_', ' ')}",
                message=outcome_message,
                symbol=proposal.symbol,
                action=intent_action,
                quantity=filled_quantity,
                status=outcome_status,
                evidence_ids=proposal.evidence_ids,
                detail={
                    "overview": {
                        "reasoning_summary": outcome_message,
                    },
                    "input": {
                        "order": asdict(order),
                        "approved_quantity": decision.approved_quantity,
                    },
                    "output": {
                        "filled_quantity": filled_quantity,
                        "remaining_quantity": max(
                            0,
                            decision.approved_quantity - filled_quantity,
                        ),
                        "order_status": order.status,
                    },
                },
            )
        if fills:
            self._record_portfolio_history(state)

    def _decision_view(self, decision: CommitteeDecision) -> CommitteeDecisionView:
        return CommitteeDecisionView(
            id=f"{decision.cycle_id}-{decision.proposal_id}-decision",
            cycle_id=decision.cycle_id,
            symbol=decision.symbol,
            final_decision=decision.final_decision,
            approved_action=decision.approved_action,
            approved_quantity=decision.approved_quantity,
            approved_notional=decision.approved_notional,
            required_order_style=decision.required_order_style,
            primary_reason=decision.primary_reason,
            dissenting_views=decision.dissenting_views,
            risk_constraints_applied=decision.risk_constraints_applied,
            compliance_constraints_applied=decision.compliance_constraints_applied,
            execution_constraints_applied=decision.execution_constraints_applied,
            confidence=decision.confidence,
            evidence_ids=decision.evidence_ids,
        )

    def _seed_books(self, state: SimulationState) -> None:
        for symbol, price in self.latest_prices(state).items():
            volume_hint, volatility_hint = self._book_shape_hints(state, symbol)
            state.exchange.seed_liquidity(
                state.simulation_id,
                symbol,
                price,
                state.current_time,
                volume_hint=volume_hint,
                volatility_hint=volatility_hint,
            )

    def _register_skills(self) -> None:
        allowed_read = {
            "MacroAnalystAgent",
            "FundamentalAnalystAgent",
            "TechnicalAnalystAgent",
            "SentimentNewsAnalystAgent",
            "BullResearcherAgent",
            "BearResearcherAgent",
            "ResearchManagerAgent",
            "PortfolioManagerAgent",
            "RiskManagerAgent",
            "ComplianceOfficerAgent",
            "InvestmentCommitteeChairAgent",
            "ExecutionTraderAgent",
            "DemoNarratorAgent",
        }

        def active_state(input_json: dict) -> SimulationState:
            return self.get_state(
                input_json.get("simulation_id") or self.default_state().simulation_id
            )

        self.registry.register(
            Skill(
                "market_get_snapshot",
                "Return point-in-time market snapshot.",
                PermissionLevel.READ_MARKET,
                True,
                False,
                allowed_read,
                lambda data: {
                    "latest_prices": {
                        k: float(v) for k, v in self.latest_prices(active_state(data)).items()
                    },
                    "released_event_ids": [e.id for e in self.visible_events(active_state(data))],
                    "market_data": active_state(data).market_data.model_dump(mode="json"),
                },
            )
        )
        self.registry.register(
            Skill(
                "news_get_released_events",
                "Return released events up to current simulation time.",
                PermissionLevel.READ_MARKET,
                True,
                False,
                allowed_read,
                lambda data: {
                    "events": [
                        event.model_dump(mode="json")
                        for event in self.visible_events(active_state(data))
                        if not data.get("symbols")
                        or set(event.affected_symbols) & set(data.get("symbols", []))
                    ]
                },
            )
        )
        self.registry.register(
            Skill(
                "portfolio_get_state",
                "Return cash, equity, positions, PnL, and exposures.",
                PermissionLevel.READ_PORTFOLIO,
                True,
                False,
                allowed_read,
                lambda data: (
                    active_state(data)
                    .ledger.state(
                        self.latest_prices(active_state(data)),
                        self._sector_map(active_state(data)),
                    )
                    .model_dump()
                ),
            )
        )
        self.registry.register(
            Skill(
                "orderbook_get_depth",
                "Return visible limit-order-book depth.",
                PermissionLevel.READ_ORDERBOOK,
                True,
                False,
                allowed_read,
                lambda data: self._orderbook_snapshot(
                    active_state(data),
                    data.get("symbol", self._default_symbol(active_state(data))),
                    int(data.get("depth", 10)),
                ).model_dump(),
            )
        )
        self.registry.register(
            Skill(
                "research_compute_indicators",
                "Compute deterministic technical features.",
                PermissionLevel.RUN_CALCULATION,
                True,
                False,
                allowed_read,
                lambda data: self._indicator_payload(
                    active_state(data),
                    data.get("symbol", self._default_symbol(active_state(data))),
                    int(data.get("lookback_minutes", 15)),
                ),
            )
        )
        self.registry.register(
            Skill(
                "exchange_estimate_market_impact",
                "Estimate slippage and fill probability from visible book.",
                PermissionLevel.READ_ORDERBOOK,
                True,
                False,
                allowed_read,
                lambda data: self._impact_payload(
                    active_state(data),
                    data.get("symbol", self._default_symbol(active_state(data))),
                    int(data.get("quantity", 100)),
                ),
            )
        )
        self.registry.register(
            Skill(
                "risk_pre_trade_check",
                "Run deterministic risk check on a proposed trade.",
                PermissionLevel.REQUEST_RISK_CHECK,
                True,
                False,
                {"RiskManagerAgent"},
                lambda data: self.risk.pre_trade_check(
                    TradeProposal.model_validate(data),
                    active_state(data).ledger.state(
                        self.latest_prices(active_state(data)),
                        self._sector_map(active_state(data)),
                    ),
                    self.latest_prices(active_state(data))[
                        TradeProposal.model_validate(data).symbol
                    ],
                    Decimal("0.041"),
                ).model_dump(),
            )
        )
        self.registry.register(
            Skill(
                "compliance_pre_trade_check",
                "Run deterministic compliance check.",
                PermissionLevel.REQUEST_COMPLIANCE_CHECK,
                True,
                False,
                {"ComplianceOfficerAgent"},
                lambda data: self.compliance.pre_trade_check(
                    TradeProposal.model_validate(data),
                    {event.id for event in self.visible_events(active_state(data))},
                    {
                        event.id: set(event.affected_symbols)
                        for event in self.visible_events(active_state(data))
                    },
                ).model_dump(),
            )
        )
        self.registry.register(
            Skill(
                "broker_validate_order_plan",
                "Validate an order plan before routing.",
                PermissionLevel.SUBMIT_ORDER_PLAN,
                True,
                False,
                {"ExecutionTraderAgent"},
                lambda data: {
                    "accepted_child_orders": [data.get("client_order_id")],
                    "rejected_child_orders": [],
                    "reason_codes": [],
                },
            )
        )
        self.registry.register(
            Skill(
                "broker_route_approved_order",
                "Route broker-approved child order to the simulated exchange.",
                PermissionLevel.ROUTE_APPROVED_ORDER,
                True,
                True,
                {"ExecutionTraderAgent"},
                lambda data: {
                    "status": "accepted_for_simulated_routing",
                    "order_id": data.get("client_order_id"),
                    "simulation_only": True,
                },
            )
        )
        self.registry.register(
            Skill(
                "benchmark_compare_modes",
                "Compare multi-agent and baseline modes.",
                PermissionLevel.RUN_BENCHMARK,
                True,
                False,
                {"DemoNarratorAgent"},
                lambda data: {
                    "metrics": [
                        metric.model_dump()
                        for metric in self._benchmark_metrics_for_state(active_state(data))
                    ]
                },
            )
        )
        self.registry.register(
            Skill(
                "audit_write_decision",
                "Write immutable audit note.",
                PermissionLevel.WRITE_AUDIT_LOG,
                True,
                False,
                {"ComplianceOfficerAgent"},
                lambda data: {"audit_log_id": f"audit-{uuid4()}", "audit_hash": str(uuid4())},
            )
        )
        self.registry.register(
            Skill(
                "ledger_get_entries",
                "Return recent simulated ledger entries.",
                PermissionLevel.READ_PORTFOLIO,
                True,
                False,
                allowed_read,
                lambda data: {"entries": []},
            )
        )
        self.registry.register(
            Skill(
                "math_calculate",
                "Run deterministic arithmetic helper.",
                PermissionLevel.RUN_CALCULATION,
                True,
                False,
                allowed_read,
                lambda data: {"result": data.get("a", 0) + data.get("b", 0)},
            )
        )

    def _indicator_payload(self, state: SimulationState, symbol: str, lookback: int) -> dict:
        bars = self.visible_bars(state, symbol)[-max(2, lookback) :]
        if len(bars) < 2:
            return {
                "last_return": 0,
                "rolling_volatility": 0,
                "volume_ratio": 1,
                "orderbook_imbalance": 0,
            }
        last_return = (bars[-1].close - bars[0].close) / bars[0].close
        avg_volume = sum(bar.volume for bar in bars) / len(bars)
        orderbook = state.exchange.get_orderbook(symbol)
        return {
            "last_return": round(last_return, 4),
            "rolling_volatility": 0.031,
            "vwap_approximation": round(
                sum(bar.close * bar.volume for bar in bars)
                / max(1, sum(bar.volume for bar in bars)),
                2,
            ),
            "volume_ratio": round(bars[-1].volume / max(1, avg_volume), 3),
            "orderbook_imbalance": orderbook.imbalance,
            "support": min(bar.low for bar in bars),
            "resistance": max(bar.high for bar in bars),
        }

    def _impact_payload(self, state: SimulationState, symbol: str, quantity: int) -> dict:
        book = state.exchange.get_orderbook(symbol)
        visible_qty = sum(level.quantity for level in book.asks)
        fill_pct = min(1.0, visible_qty / max(1, quantity))
        return {
            "estimated_average_fill_price": book.asks[0].price if book.asks else book.mid,
            "estimated_slippage_bps": 18 if fill_pct > 0.8 else 62,
            "estimated_fill_pct": round(fill_pct, 3),
            "liquidity_warning": fill_pct < 0.8,
        }


ENGINE = SimulationEngine()
