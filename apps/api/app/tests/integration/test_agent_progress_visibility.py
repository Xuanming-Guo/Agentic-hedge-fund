from __future__ import annotations

import asyncio
import json
import threading
import time
from datetime import timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from app.agents.providers import MockLLMProvider
from app.api import routes
from app.core.config import Settings
from app.main import app
from app.schemas.agent_outputs import TradeProposal
from app.schemas.market import AgentDecisionTrace, CandidateSlateItem, ConsensusSnapshot
from app.services import recording_service as recording_module
from app.services import simulation_engine
from app.services.orderbook import Order
from app.services.recording_service import RecordingService
from app.services.synthetic_data import market_open_for


class SlowMockLLMProvider(MockLLMProvider):
    async def complete_json(self, **kwargs):
        await asyncio.sleep(0.05)
        return await super().complete_json(**kwargs)


class QwenLikeProviderWithPortfolioFallback(MockLLMProvider):
    provider_name = "qwen"

    async def complete_json(self, **kwargs):
        if kwargs["agent_name"] == "PortfolioManagerAgent":
            raise ConnectionError("Connection error.")
        result = await super().complete_json(**kwargs)
        result.provider = self.provider_name
        result.model = kwargs["metadata"].get("model", "qwen-plus")
        return result


class TimedMockLLMProvider(MockLLMProvider):
    research_agents = {
        "MacroAnalystAgent",
        "TechnicalAnalystAgent",
        "SentimentNewsAnalystAgent",
        "BullResearcherAgent",
        "BearResearcherAgent",
    }

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.started: dict[str, float] = {}
        self.finished: dict[str, float] = {}
        self.active_research = 0
        self.max_active_research = 0

    async def complete_json(self, **kwargs):
        agent_name = kwargs["agent_name"]
        is_research = agent_name in self.research_agents
        with self.lock:
            self.started[agent_name] = time.perf_counter()
            if is_research:
                self.active_research += 1
                self.max_active_research = max(
                    self.max_active_research,
                    self.active_research,
                )
        try:
            await asyncio.sleep(0.06 if is_research else 0.01)
            return await super().complete_json(**kwargs)
        finally:
            with self.lock:
                self.finished[agent_name] = time.perf_counter()
                if is_research:
                    self.active_research -= 1


def _engine_without_real_keys(monkeypatch) -> simulation_engine.SimulationEngine:
    monkeypatch.setattr(
        simulation_engine,
        "get_settings",
        lambda: Settings(
            database_url="sqlite:///:memory:",
            dashscope_api_key="",
            max_parallel_agent_calls=5,
        ),
    )
    engine = simulation_engine.SimulationEngine()
    slow_provider = SlowMockLLMProvider()
    engine.llm_provider = slow_provider
    engine.orchestrator.provider = slow_provider
    return engine


def test_agent_cycle_progress_moves_from_running_to_complete(monkeypatch) -> None:
    engine = _engine_without_real_keys(monkeypatch)
    state = engine.create_simulation("2024-05-10")
    state.status = "running"
    state.current_time = market_open_for(state.scenario.display_date) - timedelta(minutes=1)

    engine.tick_market_only(state)
    started = engine.maybe_start_agent_cycle_async(state)
    running_snapshot = engine.snapshot(state.simulation_id)

    assert started is True
    assert running_snapshot.agent_cycle_status == "running"
    assert running_snapshot.active_cycle_id is not None
    assert running_snapshot.expected_llm_calls == 6

    assert state.cycle_thread is not None
    state.cycle_thread.join(timeout=5)
    complete_snapshot = engine.snapshot(state.simulation_id)

    assert complete_snapshot.agent_cycle_status == "complete"
    assert complete_snapshot.completed_llm_calls == 6
    assert complete_snapshot.last_llm_calls == 6
    assert len(complete_snapshot.candidate_slate) == len(state.instruments)
    assert [item.rank for item in complete_snapshot.candidate_slate] == list(
        range(1, len(state.instruments) + 1)
    )
    assert complete_snapshot.agent_decisions
    assert complete_snapshot.trade_tape == []
    assert any(
        decision.status == "no_trade" and decision.action == "monitor"
        for decision in complete_snapshot.agent_decisions
    )
    assert not any(
        decision.stage in {"risk_review", "compliance_review", "broker", "fill"}
        for decision in complete_snapshot.agent_decisions
    )
    assert any(item.kind == "cycle_start" for item in complete_snapshot.agent_activity_feed)
    assert any(item.kind == "agent_started" for item in complete_snapshot.agent_activity_feed)
    assert len(
        [item for item in complete_snapshot.agent_activity_feed if item.kind == "agent_completed"]
    ) == 6
    assert any(item.kind == "proposal" for item in complete_snapshot.agent_activity_feed)
    assert any(
        item.kind == "committee_decision" and item.status == "no_trade"
        for item in complete_snapshot.agent_activity_feed
    )
    llm_item = next(
        item for item in complete_snapshot.agent_activity_feed if item.kind == "agent_completed"
    )
    llm_detail = engine.agent_activity_detail(state.simulation_id, llm_item.id)
    assert "model_visible_input" in llm_detail.input
    assert "response_schema" in llm_detail.input
    assert "raw_structured_output" in llm_detail.output
    assert "validated_json" in llm_detail.output

    tool_item = next(
        item for item in complete_snapshot.agent_activity_feed if item.kind == "tool_call"
    )
    tool_detail = engine.agent_activity_detail(state.simulation_id, tool_item.id)
    assert "tool_input" in tool_detail.input
    assert "tool_output" in tool_detail.output
    orderbook_item = next(
        item
        for item in complete_snapshot.agent_activity_feed
        if item.kind == "tool_call" and "orderbook_get_depth" in item.title
    )
    orderbook_detail = engine.agent_activity_detail(state.simulation_id, orderbook_item.id)
    assert orderbook_detail.output["tool_output"]["depth_source"]
    assert orderbook_detail.output["tool_output"]["market_data_mode"]

    monitor_item = next(
        item
        for item in complete_snapshot.agent_activity_feed
        if item.kind == "committee_decision" and item.status == "no_trade"
    )
    monitor_detail = engine.agent_activity_detail(state.simulation_id, monitor_item.id)
    assert monitor_detail.output["decision"] == "no_trade"
    assert "visible_events" in monitor_detail.input


def test_snapshot_keeps_primary_provider_when_agent_falls_back(monkeypatch) -> None:
    engine = _engine_without_real_keys(monkeypatch)
    qwen_like_provider = QwenLikeProviderWithPortfolioFallback()
    engine.active_llm_provider = "qwen"
    engine.model_router.provider_name = "qwen"
    engine.llm_provider = qwen_like_provider
    engine.orchestrator.provider = qwen_like_provider
    state = engine.create_simulation("2024-05-10")
    state.status = "running"
    state.current_time = market_open_for(state.scenario.display_date) + timedelta(minutes=5)

    engine._run_agent_cycle(state, current_minute=5)
    snapshot = engine.snapshot(state.simulation_id)

    assert snapshot.configured_provider == "qwen"
    assert snapshot.active_provider == "qwen"
    assert snapshot.last_completed_provider == "mock"
    assert snapshot.last_llm_provider == "mock"
    assert snapshot.last_fallback_provider == "mock"
    assert snapshot.last_fallback_agent == "PortfolioManagerAgent"
    assert snapshot.last_fallback_reason == "Connection error."
    assert snapshot.last_llm_error is None

    fallback_item = next(
        item
        for item in snapshot.agent_activity_feed
        if item.kind == "error" and item.agent_id == "PortfolioManagerAgent"
    )
    fallback_detail = engine.agent_activity_detail(state.simulation_id, fallback_item.id)
    assert fallback_detail.overview["primary_provider"] == "qwen"
    assert fallback_detail.overview["fallback_provider"] == "mock"
    assert fallback_detail.validation["exception_type"] == "ConnectionError"
    assert fallback_detail.validation["error_category"] == "connection"


def test_multi_ticker_cycle_ranks_slate_and_routes_basket(monkeypatch) -> None:
    engine = _engine_without_real_keys(monkeypatch)
    state = engine.create_simulation("2024-05-10")
    state.status = "running"
    state.current_time = market_open_for(state.scenario.display_date) + timedelta(minutes=45)
    engine._seed_books(state)

    engine._run_agent_cycle(state, current_minute=45)
    snapshot = engine.snapshot(state.simulation_id)

    assert len(snapshot.candidate_slate) == len(state.instruments)
    assert {candidate.symbol for candidate in snapshot.candidate_slate} == {
        instrument.symbol for instrument in state.instruments
    }
    proposals = [
        decision
        for decision in snapshot.agent_decisions
        if decision.cycle_id == state.active_cycle_id and decision.stage == "proposal"
    ]
    routed_proposals = [
        proposal for proposal in proposals if proposal.action in {"buy", "sell"}
    ]
    assert 1 <= len(proposals) <= 3
    assert len(routed_proposals) <= 3
    assert snapshot.consensus[-1].symbol == "PORTFOLIO"
    assert {candidate.allocation_role for candidate in snapshot.candidate_slate} <= {
        "primary",
        "hedge",
        "relative_value",
        "watchlist",
    }
    assert any(candidate.allocation_role == "primary" for candidate in snapshot.candidate_slate)
    assert all(
        candidate.hold_reason
        for candidate in snapshot.candidate_slate
        if candidate.allocation_role == "watchlist"
    )
    for proposal in routed_proposals:
        assert any(
            decision.stage == "risk_review" and decision.symbol == proposal.symbol
            for decision in snapshot.agent_decisions
        )


def test_candidate_roles_include_primary_hedge_and_watchlist(monkeypatch) -> None:
    engine = _engine_without_real_keys(monkeypatch)
    candidates = [
        CandidateSlateItem(
            symbol="ALPH",
            rank=1,
            score=0.72,
            side_hint="buy",
            reason="event score 0.80; return 0.42%; volume 1.10x; imbalance 0.08",
            event_ids=["S1"],
            event_count=1,
            latest_price=120,
            recent_return_pct=0.42,
            volatility_pct=0.2,
            volume_ratio=1.1,
            spread_bps=8,
            orderbook_imbalance=0.08,
            sector="Technology",
            current_position=0,
            relation_notes=[],
        ),
        CandidateSlateItem(
            symbol="MSFT",
            rank=2,
            score=0.22,
            side_hint="hold",
            reason="event score 0.00; return -0.12%; volume 1.05x; imbalance -0.02",
            event_ids=[],
            event_count=0,
            latest_price=420,
            recent_return_pct=-0.12,
            volatility_pct=0.2,
            volume_ratio=1.05,
            spread_bps=9,
            orderbook_imbalance=-0.02,
            sector="Technology",
            current_position=0,
            relation_notes=[],
        ),
        CandidateSlateItem(
            symbol="JPM",
            rank=3,
            score=0.04,
            side_hint="hold",
            reason="event score 0.00; return 0.01%; volume 0.80x; imbalance 0.00",
            event_ids=[],
            event_count=0,
            latest_price=190,
            recent_return_pct=0.01,
            volatility_pct=0.1,
            volume_ratio=0.8,
            spread_bps=7,
            orderbook_imbalance=0.0,
            sector="Financials",
            current_position=0,
            relation_notes=[],
        ),
    ]

    engine._apply_allocation_roles(candidates, {"Technology": 260_000})

    assert candidates[0].allocation_role == "primary"
    assert candidates[1].allocation_role == "hedge"
    assert candidates[1].side_hint == "sell"
    assert candidates[2].allocation_role == "watchlist"
    assert candidates[2].hold_reason == "no direct event"


def test_snapshot_recovers_chat_feed_from_existing_decision_trace(monkeypatch) -> None:
    engine = _engine_without_real_keys(monkeypatch)
    state = engine.create_simulation("2024-05-10")
    state.status = "running"
    state.current_time = market_open_for(state.scenario.display_date) + timedelta(minutes=20)
    event = engine.visible_events(state)[0]
    state.agent_decisions.append(
        AgentDecisionTrace(
            id="legacy-cycle-1-committee",
            cycle_id="legacy-cycle-1",
            timestamp=state.current_time,
            agent_id="InvestmentCommitteeChairAgent",
            stage="committee",
            symbol=event.affected_symbols[0],
            action="defer",
            requested_quantity=250,
            approved_quantity=0,
            price=101.25,
            status="defer",
            rationale="Committee deferred because the existing trace lacked execution approval.",
            evidence_ids=[event.id],
        )
    )

    snapshot = engine.snapshot(state.simulation_id)

    assert snapshot.agent_activity_feed
    recovered = snapshot.agent_activity_feed[0]
    assert recovered.kind == "committee_decision"
    assert recovered.symbol == event.affected_symbols[0]
    assert recovered.validation_summary is not None
    assert "Trace recovered" in recovered.validation_summary

    detail = engine.agent_activity_detail(state.simulation_id, recovered.id)
    assert detail.overview["source"] == "reconstructed_from_trace"
    assert detail.output["status"] == "defer"
    assert detail.references[0]["id"] == event.id


def test_websocket_emits_running_agent_cycle_snapshot(monkeypatch) -> None:
    engine = _engine_without_real_keys(monkeypatch)
    monkeypatch.setattr(routes, "ENGINE", engine)
    state = engine.create_simulation("2024-05-10")
    state.status = "running"
    state.current_time = market_open_for(state.scenario.display_date) - timedelta(minutes=1)
    client = TestClient(app)

    with client.websocket_connect(f"/api/ws/simulations/{state.simulation_id}") as websocket:
        payload = websocket.receive_json()

    if state.cycle_thread is not None:
        state.cycle_thread.join(timeout=5)

    assert payload["agent_cycle_status"] == "running"
    assert payload["expected_llm_calls"] == 6
    assert "active_provider" not in payload
    assert "configured_provider" not in payload
    assert "last_llm_provider" not in payload
    assert "last_llm_model" not in payload
    assert payload["agent_decisions"] == []
    assert payload["agent_activity_feed"][0]["kind"] == "cycle_start"
    assert "provider" not in payload["agent_activity_feed"][0]
    assert "model" not in payload["agent_activity_feed"][0]
    activity_id = payload["agent_activity_feed"][0]["id"]
    detail_response = client.get(
        f"/api/simulations/{state.simulation_id}/agent-activity/{activity_id}"
    )
    missing_response = client.get(
        f"/api/simulations/{state.simulation_id}/agent-activity/not-found"
    )

    assert detail_response.status_code == 200
    assert detail_response.json()["overview"]["kind"] == "cycle_start"
    assert "provider" not in detail_response.json()["overview"]
    assert "model" not in detail_response.json()["overview"]
    assert missing_response.status_code == 404


def test_saved_recording_files_redact_provider_and_model(monkeypatch, tmp_path) -> None:
    engine = _engine_without_real_keys(monkeypatch)
    state = engine.create_simulation("2024-05-10")
    state.status = "running"
    state.current_time = market_open_for(state.scenario.display_date) + timedelta(minutes=5)

    engine._run_agent_cycle(state, current_minute=5)
    snapshot = engine.snapshot(state.simulation_id)

    monkeypatch.setattr(
        recording_module,
        "get_settings",
        lambda: Settings(
            database_url="sqlite:///:memory:",
            dashscope_api_key="",
            simulation_recordings_dir=str(tmp_path),
        ),
    )
    service = RecordingService()
    manifest = service.create_recording(
        snapshot=snapshot,
        duration_minutes=60,
        name="Redacted recording",
    )
    service.record_snapshot(
        snapshot,
        activity_details=state.activity_details,
        skill_call_details={},
    )

    recording_dir = tmp_path / manifest.recording_id
    manifest_payload = json.loads((recording_dir / "manifest.json").read_text())
    frame_snapshot = json.loads((recording_dir / "frames.ndjson").read_text().splitlines()[0])[
        "snapshot"
    ]
    first_activity = frame_snapshot["agent_activity_feed"][0]
    activity_payload = json.loads((recording_dir / "activity_details.json").read_text())
    first_detail = next(iter(activity_payload.values()))

    assert "provider" not in manifest_payload
    assert "model_summary" not in manifest_payload
    assert "active_provider" not in frame_snapshot
    assert "configured_provider" not in frame_snapshot
    assert "last_llm_provider" not in frame_snapshot
    assert "last_llm_model" not in frame_snapshot
    assert "provider" not in first_activity
    assert "model" not in first_activity
    assert "provider" not in first_detail["overview"]
    assert "model" not in first_detail["overview"]


def test_recording_service_repairs_legacy_json_with_trailing_characters(
    monkeypatch, tmp_path
) -> None:
    engine = _engine_without_real_keys(monkeypatch)
    state = engine.create_simulation("2024-05-10")
    snapshot = engine.snapshot(state.simulation_id)
    monkeypatch.setattr(
        recording_module,
        "get_settings",
        lambda: Settings(
            database_url="sqlite:///:memory:",
            dashscope_api_key="",
            simulation_recordings_dir=str(tmp_path),
        ),
    )
    service = RecordingService()
    manifest = service.create_recording(snapshot=snapshot, duration_minutes=60, name="Legacy")
    service.record_snapshot(snapshot, activity_details={}, skill_call_details={})
    recording = service.get_recording(manifest.recording_id)
    recording_dir = tmp_path / manifest.recording_id

    for sidecar in (
        "manifest.json",
        "frames.ndjson",
        "activity_details.json",
        "skill_call_details.json",
    ):
        (recording_dir / sidecar).unlink()
    (recording_dir / "recording.json").write_text(
        json.dumps(recording.model_dump(mode="json")) + "\n{}",
        encoding="utf-8",
    )

    keyframes = service.get_keyframes(manifest.recording_id)
    frames = service.get_frames(manifest.recording_id)

    assert len(keyframes) == 1
    assert keyframes[0].frame_index == 0
    assert keyframes[0].reason == "Initial frame"
    assert len(frames) == 1
    assert frames[0].snapshot.simulation_id == snapshot.simulation_id
    assert (recording_dir / "frames.ndjson").exists()
    assert (recording_dir / "manifest.json").exists()


def test_unrecoverable_recording_returns_controlled_error(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        recording_module,
        "get_settings",
        lambda: Settings(
            database_url="sqlite:///:memory:",
            dashscope_api_key="",
            simulation_recordings_dir=str(tmp_path),
        ),
    )
    service = RecordingService()
    recording_id = "rec-corrupt"
    recording_dir = tmp_path / recording_id
    recording_dir.mkdir(parents=True)
    (recording_dir / "recording.json").write_text("{not-json", encoding="utf-8")
    monkeypatch.setattr(routes, "RECORDINGS", service)
    client = TestClient(app)

    response = client.get(f"/api/recordings/{recording_id}/frames")

    assert response.status_code == 409
    assert "corrupted" in response.json()["detail"]


def test_recording_service_concurrent_reads_and_writes(monkeypatch, tmp_path) -> None:
    engine = _engine_without_real_keys(monkeypatch)
    state = engine.create_simulation("2024-05-10")
    snapshot = engine.snapshot(state.simulation_id)
    monkeypatch.setattr(
        recording_module,
        "get_settings",
        lambda: Settings(
            database_url="sqlite:///:memory:",
            dashscope_api_key="",
            simulation_recordings_dir=str(tmp_path),
        ),
    )
    service = RecordingService()
    manifest = service.create_recording(snapshot=snapshot, duration_minutes=60, name="Concurrent")
    errors: list[BaseException] = []

    def writer() -> None:
        try:
            for _ in range(8):
                service.record_snapshot(snapshot, activity_details={}, skill_call_details={})
        except BaseException as exc:
            errors.append(exc)

    def reader() -> None:
        try:
            for _ in range(8):
                service.get_frames(manifest.recording_id)
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert errors == []
    assert len(service.get_frames(manifest.recording_id)) == 8


def test_recording_keyframes_include_initial_action_and_final(
    monkeypatch, tmp_path
) -> None:
    engine = _engine_without_real_keys(monkeypatch)
    state = engine.create_simulation("2024-05-10")
    monkeypatch.setattr(
        recording_module,
        "get_settings",
        lambda: Settings(
            database_url="sqlite:///:memory:",
            dashscope_api_key="",
            simulation_recordings_dir=str(tmp_path),
        ),
    )
    service = RecordingService()
    first_snapshot = engine.snapshot(state.simulation_id)
    manifest = service.create_recording(
        snapshot=first_snapshot,
        duration_minutes=60,
        name="Keyframes",
    )
    service.record_snapshot(first_snapshot, activity_details={}, skill_call_details={})

    state.current_time += timedelta(minutes=1)
    state.agent_cycle_status = "running"
    state.active_agent = "MacroAnalystAgent"
    service.record_snapshot(
        engine.snapshot(state.simulation_id),
        activity_details={},
        skill_call_details={},
    )

    state.current_time += timedelta(minutes=1)
    service.record_snapshot(
        engine.snapshot(state.simulation_id),
        activity_details={},
        skill_call_details={},
    )
    monkeypatch.setattr(routes, "RECORDINGS", service)
    client = TestClient(app)

    keyframes = service.get_keyframes(manifest.recording_id)
    response = client.get(f"/api/recordings/{manifest.recording_id}/keyframes")
    frames_response = client.get(f"/api/recordings/{manifest.recording_id}/frames")

    assert [item.frame_index for item in keyframes] == [0, 1, 2]
    assert [item.reason for item in keyframes] == [
        "Initial frame",
        "Agent runtime transition",
        "Final frame",
    ]
    assert response.status_code == 200
    assert [
        item["frame_index"] for item in response.json()["keyframes"]
    ] == [0, 1, 2]
    assert frames_response.status_code == 200
    assert len(frames_response.json()["frames"]) == 3


def test_simulation_benchmark_endpoint_updates_live_snapshot(monkeypatch) -> None:
    engine = _engine_without_real_keys(monkeypatch)
    state = engine.create_simulation("2024-05-10")
    monkeypatch.setattr(routes, "ENGINE", engine)

    class NoopRecordings:
        def record_snapshot(self, *args, **kwargs):
            return None

    monkeypatch.setattr(routes, "RECORDINGS", NoopRecordings())
    client = TestClient(app)

    response = client.post(f"/api/simulations/{state.simulation_id}/benchmark")

    assert response.status_code == 200
    benchmark = response.json()["snapshot"]["benchmark"]
    assert benchmark["benchmark_run_id"].startswith("bench-")
    assert {metric["mode"] for metric in benchmark["metrics"]} >= {
        "multi_agent",
        "single_agent",
    }
    assert engine.get_state(state.simulation_id).benchmark is not None


def test_recording_benchmark_endpoint_scores_keyframes_without_mutating_recording(
    monkeypatch, tmp_path
) -> None:
    engine = _engine_without_real_keys(monkeypatch)
    state = engine.create_simulation("2024-05-10")
    monkeypatch.setattr(
        recording_module,
        "get_settings",
        lambda: Settings(
            database_url="sqlite:///:memory:",
            dashscope_api_key="",
            simulation_recordings_dir=str(tmp_path),
        ),
    )
    service = RecordingService()
    manifest = service.create_recording(
        snapshot=engine.snapshot(state.simulation_id),
        duration_minutes=60,
        name="Replay benchmark",
    )
    service.record_snapshot(
        engine.snapshot(state.simulation_id),
        activity_details={},
        skill_call_details={},
    )
    state.current_time += timedelta(minutes=1)
    state.agent_cycle_status = "running"
    state.active_agent = "MacroAnalystAgent"
    service.record_snapshot(
        engine.snapshot(state.simulation_id),
        activity_details={},
        skill_call_details={},
    )
    before_frames = service.get_frames(manifest.recording_id)
    monkeypatch.setattr(routes, "ENGINE", engine)
    monkeypatch.setattr(routes, "RECORDINGS", service)
    client = TestClient(app)

    response = client.post(f"/api/recordings/{manifest.recording_id}/benchmark")

    after_frames = service.get_frames(manifest.recording_id)
    assert response.status_code == 200
    payload = response.json()
    assert payload["recording_id"] == manifest.recording_id
    assert payload["scope"] == "keyframes"
    assert [item["frame_index"] for item in payload["items"]] == [0, 1]
    assert payload["summary"]["benchmark_run_id"] == payload["items"][-1]["benchmark"][
        "benchmark_run_id"
    ]
    assert {metric["mode"] for metric in payload["summary"]["metrics"]} >= {
        "multi_agent",
        "single_agent",
    }
    assert len(after_frames) == len(before_frames)
    assert all(frame.snapshot.benchmark is None for frame in after_frames)


def test_stop_and_save_persists_final_benchmark(monkeypatch, tmp_path) -> None:
    engine = _engine_without_real_keys(monkeypatch)
    state = engine.create_simulation("2024-05-10")
    monkeypatch.setattr(
        recording_module,
        "get_settings",
        lambda: Settings(
            database_url="sqlite:///:memory:",
            dashscope_api_key="",
            simulation_recordings_dir=str(tmp_path),
        ),
    )
    service = RecordingService()
    manifest = service.create_recording(
        snapshot=engine.snapshot(state.simulation_id),
        duration_minutes=60,
        name="Auto benchmark save",
    )
    monkeypatch.setattr(routes, "ENGINE", engine)
    monkeypatch.setattr(routes, "RECORDINGS", service)
    client = TestClient(app)

    response = client.post(f"/api/simulations/{state.simulation_id}/stop-and-save")

    assert response.status_code == 200
    assert response.json()["snapshot"]["benchmark"] is not None
    assert service.latest_snapshot(manifest.recording_id).benchmark is not None


def test_recording_completion_persists_auto_benchmark(monkeypatch, tmp_path) -> None:
    engine = _engine_without_real_keys(monkeypatch)
    state = engine.create_simulation("2024-05-10")
    monkeypatch.setattr(
        recording_module,
        "get_settings",
        lambda: Settings(
            database_url="sqlite:///:memory:",
            dashscope_api_key="",
            simulation_recordings_dir=str(tmp_path),
        ),
    )
    service = RecordingService()
    manifest = service.create_recording(
        snapshot=engine.snapshot(state.simulation_id),
        duration_minutes=1,
        name="Auto benchmark complete",
    )
    monkeypatch.setattr(routes, "ENGINE", engine)
    monkeypatch.setattr(routes, "RECORDINGS", service)

    state.current_time += timedelta(minutes=1)
    routes._record_snapshot(engine.snapshot(state.simulation_id))

    saved = service.latest_snapshot(manifest.recording_id)
    assert saved.benchmark is not None
    assert service.get_manifest(manifest.recording_id).status == "complete"


def test_websocket_keeps_streaming_when_recording_persistence_fails(monkeypatch) -> None:
    engine = _engine_without_real_keys(monkeypatch)
    monkeypatch.setattr(routes, "ENGINE", engine)
    state = engine.create_simulation("2024-05-10")
    state.status = "running"
    state.current_time = market_open_for(state.scenario.display_date) - timedelta(minutes=1)

    class FailingRecordings:
        def record_snapshot(self, *args, **kwargs):
            raise RuntimeError("disk unavailable")

    monkeypatch.setattr(routes, "RECORDINGS", FailingRecordings())
    client = TestClient(app)

    with client.websocket_connect(f"/api/ws/simulations/{state.simulation_id}") as websocket:
        payload = websocket.receive_json()

    if state.cycle_thread is not None:
        state.cycle_thread.join(timeout=5)

    assert payload["simulation_id"] == state.simulation_id


def test_committee_uses_live_consensus_and_records_portfolio_history(monkeypatch) -> None:
    engine = _engine_without_real_keys(monkeypatch)
    state = engine.create_simulation("2024-05-10")
    state.status = "running"
    open_time = market_open_for(state.scenario.display_date)

    state.current_time = open_time + timedelta(minutes=5)
    engine._seed_books(state)
    echo_event = engine.visible_events(state)[0]
    state.consensus.append(
        ConsensusSnapshot(
            symbol="ECHO",
            consensus_direction="bearish",
            consensus_strength=0.74,
            disagreement_score=0.25,
            uncertainty_score=0.26,
            movers=["ResearchManagerAgent"],
        )
    )
    engine._review_and_execute(
        state,
        "manual-cycle-live-consensus",
        TradeProposal(
            proposal_id="manual-live-consensus",
            symbol="ECHO",
            side="sell",
            quantity=100,
            max_notional=10_000,
            rationale="Released macro event pressures rate-sensitive financials.",
            evidence_ids=[echo_event.id],
            confidence=0.5,
        ),
    )

    state.current_time = open_time + timedelta(minutes=45)
    engine._seed_books(state)
    alph_event = [
        event for event in engine.visible_events(state) if "ALPH" in event.affected_symbols
    ][0]
    engine._review_and_execute(
        state,
        "manual-cycle-approve",
        TradeProposal(
            proposal_id="manual-approve",
            symbol="ALPH",
            side="buy",
            quantity=100,
            max_notional=10_000,
            rationale="Released company news supports a small cloud-demand probe trade.",
            evidence_ids=[alph_event.id],
            confidence=0.82,
        ),
    )

    snapshot = engine.snapshot(state.simulation_id)
    committee_items = [
        item for item in snapshot.agent_activity_feed if item.kind == "committee_decision"
    ]

    assert any(
        item.symbol == "ECHO" and item.status in {"approve", "approve_resized"}
        for item in committee_items
    )
    assert any(
        item.symbol == "ALPH" and item.status in {"approve", "approve_resized"}
        for item in committee_items
    )
    assert any(
        item.kind == "broker_route" and item.symbol == "ALPH"
        for item in snapshot.agent_activity_feed
    )
    echo_decision = next(item for item in committee_items if item.symbol == "ECHO")
    echo_detail = engine.agent_activity_detail(state.simulation_id, echo_decision.id)
    assert echo_detail.input["disagreement_score"] == 0.25
    assert echo_detail.input["impact_bps"] < 45
    assert snapshot.portfolio_history
    assert snapshot.portfolio_history[-1].gross_exposure > 0


def test_approved_buy_fills_and_creates_long_position(monkeypatch) -> None:
    engine = _engine_without_real_keys(monkeypatch)
    state = engine.create_simulation("2024-05-10")
    state.status = "running"
    open_time = market_open_for(state.scenario.display_date)
    state.current_time = open_time + timedelta(minutes=45)
    engine._seed_books(state)
    alph_event = next(
        event for event in engine.visible_events(state) if "ALPH" in event.affected_symbols
    )

    engine._review_and_execute(
        state,
        "manual-cycle-buy-fill",
        TradeProposal(
            proposal_id="manual-cycle-buy-fill-ALPH-proposal-1",
            symbol="ALPH",
            side="buy",
            quantity=100,
            max_notional=10_000,
            rationale="Released ALPH evidence supports a small long.",
            evidence_ids=[alph_event.id],
            confidence=0.82,
        ),
    )

    snapshot = engine.snapshot(state.simulation_id)
    position = next(
        position for position in snapshot.portfolio.positions if position.symbol == "ALPH"
    )

    assert position.quantity > 0
    assert any(
        item.kind == "fill" and item.symbol == "ALPH"
        for item in snapshot.agent_activity_feed
    )
    assert any(trade.symbol == "ALPH" and trade.side == "buy" for trade in snapshot.trade_tape)


def test_approved_sell_fills_and_creates_short_position(monkeypatch) -> None:
    engine = _engine_without_real_keys(monkeypatch)
    state = engine.create_simulation("2024-05-10")
    state.status = "running"
    open_time = market_open_for(state.scenario.display_date)
    state.current_time = open_time + timedelta(minutes=5)
    engine._seed_books(state)
    echo_event = next(
        event for event in engine.visible_events(state) if "ECHO" in event.affected_symbols
    )

    engine._review_and_execute(
        state,
        "manual-cycle-short-fill",
        TradeProposal(
            proposal_id="manual-cycle-short-fill-ECHO-proposal-1",
            symbol="ECHO",
            side="sell",
            quantity=100,
            max_notional=10_000,
            rationale="Released ECHO evidence supports a small short.",
            evidence_ids=[echo_event.id],
            confidence=0.82,
        ),
    )

    snapshot = engine.snapshot(state.simulation_id)
    position = next(
        position for position in snapshot.portfolio.positions if position.symbol == "ECHO"
    )

    assert position.quantity < 0
    assert any(trade.symbol == "ECHO" and trade.side == "sell" for trade in snapshot.trade_tape)


def test_hedge_leg_can_use_released_basket_evidence(monkeypatch) -> None:
    engine = _engine_without_real_keys(monkeypatch)
    state = engine.create_simulation("2024-05-10")
    state.status = "running"
    open_time = market_open_for(state.scenario.display_date)
    state.current_time = open_time + timedelta(minutes=45)
    engine._seed_books(state)
    alph_event = next(
        event for event in engine.visible_events(state) if "ALPH" in event.affected_symbols
    )

    engine._review_and_execute(
        state,
        "manual-cycle-hedge-fill",
        TradeProposal(
            proposal_id="manual-cycle-hedge-fill-BRAV-proposal-1",
            symbol="BRAV",
            side="sell",
            allocation_role="hedge",
            quantity=100,
            max_notional=10_000,
            rationale="Small hedge leg against catalyst-led portfolio exposure.",
            evidence_ids=[alph_event.id],
            confidence=0.72,
        ),
    )

    snapshot = engine.snapshot(state.simulation_id)
    compliance = next(
        item
        for item in snapshot.agent_activity_feed
        if item.kind == "compliance_review" and item.symbol == "BRAV"
    )
    position = next(
        position for position in snapshot.portfolio.positions if position.symbol == "BRAV"
    )

    assert compliance.status == "complete"
    assert position.quantity < 0
    assert any(trade.symbol == "BRAV" and trade.side == "sell" for trade in snapshot.trade_tape)


def test_approved_buy_partially_fills_and_cancels_remainder(monkeypatch) -> None:
    engine = _engine_without_real_keys(monkeypatch)
    state = engine.create_simulation("2024-05-10")
    state.status = "running"
    open_time = market_open_for(state.scenario.display_date)
    state.current_time = open_time + timedelta(minutes=45)
    engine._seed_books(state)
    monkeypatch.setattr(engine, "_estimate_execution_impact_bps", lambda *_: 5.0)
    price = engine.latest_prices(state)["ALPH"]
    book = state.exchange.get_book("ALPH")
    book.buy_orders = []
    book.sell_orders = []
    state.exchange.sequence += 1
    book.submit_order(
        Order(
            id="ask-small-liquidity",
            simulation_id=state.simulation_id,
            symbol="ALPH",
            owner_type="background_market_maker",
            owner_id="market",
            side="sell",
            order_type="limit",
            quantity=5,
            remaining_quantity=5,
            limit_price=price + Decimal("0.01"),
            stop_price=None,
            time_in_force="DAY",
            status="open",
            created_at_seq=state.exchange.sequence,
            client_order_id="ask-small-liquidity",
        )
    )
    alph_event = next(
        event for event in engine.visible_events(state) if "ALPH" in event.affected_symbols
    )

    engine._review_and_execute(
        state,
        "manual-cycle-partial-fill",
        TradeProposal(
            proposal_id="manual-cycle-partial-fill-ALPH-proposal-1",
            symbol="ALPH",
            side="buy",
            quantity=100,
            max_notional=10_000,
            rationale="Released ALPH evidence but limited visible liquidity.",
            evidence_ids=[alph_event.id],
            confidence=0.82,
        ),
    )

    snapshot = engine.snapshot(state.simulation_id)
    partial = next(
        decision for decision in snapshot.agent_decisions if decision.status == "partially_filled"
    )
    position = next(
        position for position in snapshot.portfolio.positions if position.symbol == "ALPH"
    )

    assert partial.filled_quantity == 5
    assert position.quantity == 5


def test_approved_buy_without_visible_liquidity_records_unfilled(monkeypatch) -> None:
    engine = _engine_without_real_keys(monkeypatch)
    state = engine.create_simulation("2024-05-10")
    state.status = "running"
    open_time = market_open_for(state.scenario.display_date)
    state.current_time = open_time + timedelta(minutes=45)
    engine._seed_books(state)
    monkeypatch.setattr(engine, "_estimate_execution_impact_bps", lambda *_: 5.0)
    book = state.exchange.get_book("ALPH")
    book.buy_orders = []
    book.sell_orders = []
    alph_event = next(
        event for event in engine.visible_events(state) if "ALPH" in event.affected_symbols
    )

    engine._review_and_execute(
        state,
        "manual-cycle-unfilled",
        TradeProposal(
            proposal_id="manual-cycle-unfilled-ALPH-proposal-1",
            symbol="ALPH",
            side="buy",
            quantity=100,
            max_notional=10_000,
            rationale="Released ALPH evidence but no visible ask liquidity.",
            evidence_ids=[alph_event.id],
            confidence=0.82,
        ),
    )

    snapshot = engine.snapshot(state.simulation_id)

    assert not snapshot.portfolio.positions
    assert any(decision.status == "unfilled" for decision in snapshot.agent_decisions)


def test_review_sanitizes_mixed_symbol_evidence_before_compliance(monkeypatch) -> None:
    engine = _engine_without_real_keys(monkeypatch)
    state = engine.create_simulation("2024-05-10")
    state.status = "running"
    open_time = market_open_for(state.scenario.display_date)
    state.current_time = open_time + timedelta(minutes=50)
    engine._seed_books(state)
    visible = engine.visible_events(state)
    brav_event = next(event for event in visible if "BRAV" in event.affected_symbols)
    alph_event = next(event for event in visible if "ALPH" in event.affected_symbols)

    engine._review_and_execute(
        state,
        "manual-cycle-mixed-evidence",
        TradeProposal(
            proposal_id="manual-cycle-mixed-evidence-ALPH-proposal-1",
            symbol="ALPH",
            side="buy",
            quantity=100,
            max_notional=10_000,
            rationale="Provider mixed a valid ALPH event with an irrelevant BRAV event.",
            evidence_ids=[brav_event.id, alph_event.id],
            confidence=0.82,
        ),
    )

    snapshot = engine.snapshot(state.simulation_id)
    compliance = next(
        item
        for item in snapshot.agent_activity_feed
        if item.kind == "compliance_review" and item.symbol == "ALPH"
    )
    committee = next(
        item
        for item in snapshot.agent_activity_feed
        if item.kind == "committee_decision" and item.symbol == "ALPH"
    )
    compliance_detail = engine.agent_activity_detail(state.simulation_id, compliance.id)
    committee_detail = engine.agent_activity_detail(state.simulation_id, committee.id)

    assert compliance.status == "complete"
    assert committee.status in {"approve", "approve_resized"}
    assert compliance.evidence_ids == [alph_event.id]
    assert compliance_detail.input["evidence_hygiene"]["original_evidence_ids"] == [
        brav_event.id,
        alph_event.id,
    ]
    assert compliance_detail.input["evidence_hygiene"]["sanitized_evidence_ids"] == [
        alph_event.id
    ]
    assert compliance_detail.input["evidence_hygiene"]["dropped_irrelevant_evidence_ids"] == [
        brav_event.id
    ]
    assert committee_detail.input["evidence_hygiene"]["sanitized_evidence_ids"] == [
        alph_event.id
    ]


def test_review_uses_candidate_symbol_evidence_when_provider_ids_are_wrong(
    monkeypatch,
) -> None:
    engine = _engine_without_real_keys(monkeypatch)
    state = engine.create_simulation("2024-05-10")
    state.status = "running"
    open_time = market_open_for(state.scenario.display_date)
    state.current_time = open_time + timedelta(minutes=50)
    engine._seed_books(state)
    visible = engine.visible_events(state)
    brav_event = next(event for event in visible if "BRAV" in event.affected_symbols)
    alph_event = next(event for event in visible if "ALPH" in event.affected_symbols)
    state.candidate_slate = [
        CandidateSlateItem(
            symbol="ALPH",
            rank=1,
            score=0.82,
            side_hint="buy",
            reason="Synthetic ALPH catalyst.",
            event_ids=[alph_event.id],
            event_count=1,
            latest_price=float(engine.latest_prices(state)["ALPH"]),
            recent_return_pct=0.5,
            volatility_pct=0.1,
            volume_ratio=1.1,
            spread_bps=8,
            orderbook_imbalance=0.0,
            sector="Technology",
            current_position=0,
            relation_notes=[],
        )
    ]

    engine._review_and_execute(
        state,
        "manual-cycle-candidate-evidence",
        TradeProposal(
            proposal_id="manual-cycle-candidate-evidence-ALPH-proposal-1",
            symbol="ALPH",
            side="buy",
            quantity=100,
            max_notional=10_000,
            rationale="Provider cited only a BRAV event, but slate has direct ALPH evidence.",
            evidence_ids=[brav_event.id],
            confidence=0.82,
        ),
    )

    snapshot = engine.snapshot(state.simulation_id)
    compliance = next(
        item
        for item in snapshot.agent_activity_feed
        if item.kind == "compliance_review" and item.symbol == "ALPH"
    )
    detail = engine.agent_activity_detail(state.simulation_id, compliance.id)

    assert compliance.status == "complete"
    assert compliance.evidence_ids == [alph_event.id]
    assert detail.input["evidence_hygiene"]["original_evidence_ids"] == [brav_event.id]
    assert detail.input["evidence_hygiene"]["sanitized_evidence_ids"] == [alph_event.id]
    assert detail.input["evidence_hygiene"]["dropped_irrelevant_evidence_ids"] == [
        brav_event.id
    ]


def test_review_without_direct_or_candidate_evidence_still_rejects_compliance(
    monkeypatch,
) -> None:
    engine = _engine_without_real_keys(monkeypatch)
    state = engine.create_simulation("2024-05-10")
    state.status = "running"
    open_time = market_open_for(state.scenario.display_date)
    state.current_time = open_time + timedelta(minutes=50)
    engine._seed_books(state)
    brav_event = next(
        event for event in engine.visible_events(state) if "BRAV" in event.affected_symbols
    )

    engine._review_and_execute(
        state,
        "manual-cycle-no-direct-evidence",
        TradeProposal(
            proposal_id="manual-cycle-no-direct-evidence-ALPH-proposal-1",
            symbol="ALPH",
            side="buy",
            quantity=100,
            max_notional=10_000,
            rationale="Provider cited only irrelevant evidence and slate has no ALPH evidence.",
            evidence_ids=[brav_event.id],
            confidence=0.82,
        ),
    )

    snapshot = engine.snapshot(state.simulation_id)
    compliance = next(
        item
        for item in snapshot.agent_activity_feed
        if item.kind == "compliance_review" and item.symbol == "ALPH"
    )
    committee = next(
        item
        for item in snapshot.agent_activity_feed
        if item.kind == "committee_decision" and item.symbol == "ALPH"
    )

    assert compliance.status == "rejected"
    assert compliance.evidence_ids == []
    assert committee.status == "reject"


def test_research_agents_run_in_parallel_before_portfolio(monkeypatch) -> None:
    engine = _engine_without_real_keys(monkeypatch)
    timed_provider = TimedMockLLMProvider()
    engine.llm_provider = timed_provider
    engine.orchestrator.provider = timed_provider
    state = engine.create_simulation("2024-05-10")
    state.status = "running"
    state.current_time = market_open_for(state.scenario.display_date) + timedelta(minutes=5)

    engine._run_agent_cycle(state, current_minute=5)

    for agent_name in TimedMockLLMProvider.research_agents:
        assert agent_name in timed_provider.started
        assert agent_name in timed_provider.finished
    assert timed_provider.max_active_research > 1
    assert "PortfolioManagerAgent" in timed_provider.started
    assert timed_provider.started["PortfolioManagerAgent"] >= max(
        timed_provider.finished[agent_name]
        for agent_name in TimedMockLLMProvider.research_agents
    )
    assert state.completed_llm_calls == 6
    portfolio_activity = next(
        item
        for item in state.agent_activity_feed
        if item.kind == "agent_completed" and item.agent_id == "PortfolioManagerAgent"
    )
    portfolio_detail = engine.agent_activity_detail(state.simulation_id, portfolio_activity.id)
    assert "research_outputs" in portfolio_detail.input["model_visible_input"]
    assert "consensus" in portfolio_detail.input["model_visible_input"]
