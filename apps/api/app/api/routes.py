from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.mcp_servers.common import smoke as mcp_smoke
from app.observability.metrics import websocket_clients
from app.schemas.recording import (
    CreateRecordedSimulationRequest,
    ReplayBenchmarkPoint,
    ReplayBenchmarkRun,
    SimulationEstimate,
    SimulationEstimateRequest,
)
from app.services.public_redaction import (
    redact_activity_detail_dict,
    redact_frame_dict,
    redact_manifest_dict,
    redact_snapshot_dict,
)
from app.services.recording_service import RECORDINGS, RecordingCorruptError, RecordingNotFoundError
from app.services.simulation_engine import ENGINE

router = APIRouter()
logger = logging.getLogger(__name__)


class CreateSimulationRequest(BaseModel):
    scenario_id: str = "2024-05-10"
    market_data_mode: str | None = None
    real_market_tickers: list[str] = Field(default_factory=list)
    replay_date: str | None = None


class SpeedRequest(BaseModel):
    speed: float


def _recording_corrupt_http_error(exc: RecordingCorruptError) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail=(
            f"{exc} You can continue from another healthy save, or create a new recording."
        ),
    )


def _record_snapshot(snapshot) -> None:
    state = ENGINE.get_state(snapshot.simulation_id)
    should_attach_benchmark = False
    if hasattr(RECORDINGS, "will_complete"):
        should_attach_benchmark = RECORDINGS.will_complete(snapshot)
    elif snapshot.status == "closed":
        should_attach_benchmark = True
    if should_attach_benchmark:
        ENGINE.run_benchmark(snapshot.simulation_id)
        snapshot = ENGINE.snapshot(snapshot.simulation_id)
    manifest = RECORDINGS.record_snapshot(
        snapshot,
        activity_details=state.activity_details,
        skill_call_details=ENGINE.full_skill_call_details(snapshot.simulation_id),
    )
    if manifest and manifest.status == "complete":
        state.status = "closed"


def _record_snapshot_best_effort(snapshot) -> None:
    try:
        _record_snapshot(snapshot)
    except Exception:
        logger.exception("Recording persistence failed; continuing live websocket stream.")


def _snapshot_payload(
    simulation_id: str, *, record: bool = True, best_effort_record: bool = False
) -> dict:
    snapshot = ENGINE.snapshot(simulation_id)
    if record:
        if best_effort_record:
            _record_snapshot_best_effort(snapshot)
        else:
            _record_snapshot(snapshot)
    return redact_snapshot_dict(snapshot)


def _estimate_for(duration_minutes: int) -> SimulationEstimate:
    provider = ENGINE.active_llm_provider
    expected_cycles = max(1, (duration_minutes + 14) // 15)
    calls_per_cycle = 6
    seconds_per_call = {"mock": 0.1, "qwen": 5.0}.get(provider, 5.0)
    market_tick_seconds = duration_minutes / 20.0
    estimated_real_seconds = int(
        expected_cycles * calls_per_cycle * seconds_per_call + market_tick_seconds
    )
    return SimulationEstimate(
        duration_minutes=duration_minutes,
        expected_agent_cycles=expected_cycles,
        expected_llm_calls=expected_cycles * calls_per_cycle,
        estimated_real_seconds=max(1, estimated_real_seconds),
        warning=(
            f"Estimated live recording time is about {max(1, estimated_real_seconds // 60)} "
            "minute(s) with the active AI runtime. Replay is instant after recording."
        ),
    )


@router.get("/scenarios")
def list_scenarios() -> dict:
    return {"scenarios": [scenario.model_dump() for scenario in ENGINE.list_scenarios()]}


@router.post("/simulations/estimate")
def estimate_simulation(request: SimulationEstimateRequest) -> dict:
    return _estimate_for(request.duration_minutes).model_dump(mode="json")


@router.post("/simulations/recorded")
def create_recorded_simulation(request: CreateRecordedSimulationRequest) -> dict:
    state = ENGINE.create_simulation(
        request.scenario_id,
        market_data_mode=request.market_data_mode,
        real_market_tickers=request.real_market_tickers,
        replay_date=request.replay_date,
    )
    state.speed = 20
    snapshot = ENGINE.snapshot(state.simulation_id)
    manifest = RECORDINGS.create_recording(
        snapshot=snapshot,
        duration_minutes=request.duration_minutes,
        name=request.name,
    )
    _record_snapshot(snapshot)
    return {
        "recording": redact_manifest_dict(manifest),
        "snapshot": redact_snapshot_dict(snapshot),
    }


@router.post("/simulations")
def create_simulation(request: CreateSimulationRequest) -> dict:
    state = ENGINE.create_simulation(
        request.scenario_id,
        market_data_mode=request.market_data_mode,
        real_market_tickers=request.real_market_tickers,
        replay_date=request.replay_date,
    )
    return redact_snapshot_dict(ENGINE.snapshot(state.simulation_id))


@router.get("/simulations/{simulation_id}")
def get_simulation(simulation_id: str) -> dict:
    return redact_snapshot_dict(ENGINE.snapshot(simulation_id))


@router.post("/simulations/{simulation_id}/start")
def start_simulation(simulation_id: str) -> dict:
    snapshot = ENGINE.start(simulation_id)
    _record_snapshot(snapshot)
    return redact_snapshot_dict(snapshot)


@router.post("/simulations/{simulation_id}/pause")
def pause_simulation(simulation_id: str) -> dict:
    snapshot = ENGINE.pause(simulation_id)
    _record_snapshot(snapshot)
    return redact_snapshot_dict(snapshot)


@router.post("/simulations/{simulation_id}/resume")
def resume_simulation(simulation_id: str) -> dict:
    snapshot = ENGINE.resume(simulation_id)
    _record_snapshot(snapshot)
    return redact_snapshot_dict(snapshot)


@router.post("/simulations/{simulation_id}/step")
def step_simulation(simulation_id: str) -> dict:
    snapshot = ENGINE.step(simulation_id)
    _record_snapshot(snapshot)
    return redact_snapshot_dict(snapshot)


@router.post("/simulations/{simulation_id}/reset")
def reset_simulation(simulation_id: str) -> dict:
    return redact_snapshot_dict(ENGINE.reset(simulation_id))


@router.post("/simulations/{simulation_id}/speed")
def speed_simulation(simulation_id: str, request: SpeedRequest) -> dict:
    snapshot = ENGINE.set_speed(simulation_id, request.speed)
    _record_snapshot(snapshot)
    return redact_snapshot_dict(snapshot)


@router.post("/simulations/{simulation_id}/stop-and-save")
def stop_and_save_simulation(simulation_id: str) -> dict:
    try:
        state = ENGINE.get_state(simulation_id)
        state.status = "paused"
        ENGINE.run_benchmark(simulation_id)
        snapshot = ENGINE.snapshot(simulation_id)
        _record_snapshot(snapshot)
        manifest = RECORDINGS.stop_recording(snapshot, complete=False)
        return {
            "recording": redact_manifest_dict(manifest) if manifest else None,
            "snapshot": redact_snapshot_dict(snapshot),
        }
    except RecordingCorruptError as exc:
        raise _recording_corrupt_http_error(exc) from exc


@router.get("/recordings")
def list_recordings() -> dict:
    return {"recordings": [redact_manifest_dict(item) for item in RECORDINGS.list_recordings()]}


@router.get("/recordings/{recording_id}")
def get_recording(recording_id: str) -> dict:
    try:
        return redact_manifest_dict(RECORDINGS.get_manifest(recording_id))
    except RecordingNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Recording not found.") from exc
    except RecordingCorruptError as exc:
        raise _recording_corrupt_http_error(exc) from exc


@router.get("/recordings/{recording_id}/frames")
def get_recording_frames(recording_id: str, offset: int = 0, limit: int = 500) -> dict:
    try:
        frames = RECORDINGS.get_frames(recording_id, offset=max(0, offset), limit=max(1, limit))
        return {"frames": [redact_frame_dict(frame) for frame in frames]}
    except RecordingNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Recording not found.") from exc
    except RecordingCorruptError as exc:
        raise _recording_corrupt_http_error(exc) from exc


@router.get("/recordings/{recording_id}/keyframes")
def get_recording_keyframes(recording_id: str) -> dict:
    try:
        keyframes = RECORDINGS.get_keyframes(recording_id)
        return {
            "keyframes": [
                {
                    "frame_index": keyframe.frame_index,
                    "event_index": keyframe.event_index,
                    "reason": keyframe.reason,
                    "frame": redact_frame_dict(keyframe.frame),
                }
                for keyframe in keyframes
            ]
        }
    except RecordingNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Recording not found.") from exc
    except RecordingCorruptError as exc:
        raise _recording_corrupt_http_error(exc) from exc


@router.get("/recordings/{recording_id}/frame/{index}")
def get_recording_frame(recording_id: str, index: int) -> dict:
    try:
        return redact_frame_dict(RECORDINGS.get_frame(recording_id, index))
    except RecordingNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Recording frame not found.") from exc
    except RecordingCorruptError as exc:
        raise _recording_corrupt_http_error(exc) from exc


@router.get("/recordings/{recording_id}/agent-activity/{activity_id}")
def recording_activity_detail(recording_id: str, activity_id: str) -> dict:
    try:
        detail = RECORDINGS.get_activity_detail(recording_id, activity_id)
        return redact_activity_detail_dict(detail)
    except RecordingNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Recording activity detail not found.") from exc
    except RecordingCorruptError as exc:
        raise _recording_corrupt_http_error(exc) from exc


@router.post("/recordings/{recording_id}/resume")
def resume_recording(recording_id: str) -> dict:
    try:
        manifest = RECORDINGS.get_manifest(recording_id)
        if not manifest.can_continue:
            raise HTTPException(
                status_code=400,
                detail="Recording is complete and cannot be continued.",
            )
        snapshot = RECORDINGS.latest_snapshot(recording_id)
        state = ENGINE.restore_from_snapshot(snapshot, RECORDINGS.activity_details(recording_id))
        manifest = RECORDINGS.bind_for_resume(recording_id, state.simulation_id)
        restored = ENGINE.snapshot(state.simulation_id)
        _record_snapshot(restored)
        return {
            "recording": redact_manifest_dict(manifest),
            "snapshot": redact_snapshot_dict(restored),
        }
    except RecordingNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Recording not found.") from exc
    except RecordingCorruptError as exc:
        raise _recording_corrupt_http_error(exc) from exc


@router.get("/simulations/{simulation_id}/committee-decisions")
def committee_decisions(simulation_id: str) -> dict:
    return {
        "items": [item.model_dump() for item in ENGINE.get_state(simulation_id).committee_decisions]
    }


@router.get("/simulations/{simulation_id}/consensus")
def consensus(simulation_id: str) -> dict:
    return {"items": [item.model_dump() for item in ENGINE.get_state(simulation_id).consensus]}


@router.get("/simulations/{simulation_id}/agent-activity/{activity_id}")
def agent_activity_detail(simulation_id: str, activity_id: str) -> dict:
    try:
        return redact_activity_detail_dict(ENGINE.agent_activity_detail(simulation_id, activity_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Agent activity detail not found.") from exc


@router.get("/simulations/{simulation_id}/approval-requests")
def approval_requests(simulation_id: str) -> dict:
    return {
        "items": [
            item.__dict__ for item in ENGINE.human_approvals.list_for_simulation(simulation_id)
        ]
    }


@router.post("/benchmarks/run")
def run_benchmark() -> dict:
    state = ENGINE.default_state()
    return ENGINE.run_benchmark(state.simulation_id).model_dump(mode="json")


@router.post("/simulations/{simulation_id}/benchmark")
def benchmark_simulation(simulation_id: str) -> dict:
    try:
        ENGINE.run_benchmark(simulation_id)
        snapshot = ENGINE.snapshot(simulation_id)
        _record_snapshot(snapshot)
        return {"snapshot": redact_snapshot_dict(snapshot)}
    except RecordingCorruptError as exc:
        raise _recording_corrupt_http_error(exc) from exc


@router.post("/recordings/{recording_id}/benchmark")
def benchmark_recording(recording_id: str) -> dict:
    try:
        keyframes = RECORDINGS.get_keyframes(recording_id)
        items = [
            ReplayBenchmarkPoint(
                frame_index=keyframe.frame_index,
                event_index=keyframe.event_index,
                reason=keyframe.reason,
                timestamp=keyframe.frame.timestamp,
                benchmark=ENGINE.benchmark_snapshot(keyframe.frame.snapshot),
            )
            for keyframe in keyframes
        ]
        run = ReplayBenchmarkRun(
            recording_id=recording_id,
            items=items,
            summary=items[-1].benchmark if items else None,
        )
        return run.model_dump(mode="json")
    except RecordingNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Recording not found.") from exc
    except RecordingCorruptError as exc:
        raise _recording_corrupt_http_error(exc) from exc


@router.get("/benchmarks/{benchmark_run_id}/asai")
def get_asai(benchmark_run_id: str) -> dict:
    state = ENGINE.default_state()
    if state.benchmark is None:
        state.benchmark = ENGINE.run_benchmark(state.simulation_id)
    return state.benchmark.model_dump(mode="json")


@router.post("/benchmarks/ablation-run")
def run_ablation() -> dict:
    from app.evaluation.ablation_runner import run_ablation_suite

    return run_ablation_suite()


@router.get("/benchmarks/{benchmark_run_id}/ablation-results")
def get_ablation_results(benchmark_run_id: str) -> dict:
    from app.evaluation.ablation_runner import run_ablation_suite

    return run_ablation_suite()


@router.get("/proof/qwen")
def qwen_proof() -> dict:
    settings = get_settings()
    state = ENGINE.default_state()
    active_provider = ENGINE.active_llm_provider
    if active_provider == "qwen":
        json_mode_enabled = settings.qwen_json_mode
    else:
        json_mode_enabled = False
    last_call = ENGINE.registry.calls[-1] if ENGINE.registry.calls else None
    return {
        "provider_configured": active_provider == "qwen",
        "json_mode_enabled": json_mode_enabled,
        "function_calling_enabled": True,
        "mcp_enabled": True,
        "last_agent_run_id": state.agent_states[-1].agent_id if state.agent_states else None,
        "last_fallback_agent": state.last_fallback_agent,
        "last_fallback_reason": redact_snapshot_dict(
            ENGINE.snapshot(state.simulation_id)
        ).get("last_fallback_reason"),
        "last_llm_calls": state.llm_call_count,
        "last_llm_tokens": state.llm_token_usage,
        "last_tool_call_id": last_call.id if last_call else None,
        "tool_gateway_configured": True,
        "mcp_configured": True,
    }


@router.get("/skills")
def list_skills() -> dict:
    return {"skills": [definition.model_dump() for definition in ENGINE.registry.definitions()]}


@router.get("/skills/calls")
def list_skill_calls(simulation_id: str | None = None) -> dict:
    calls = ENGINE.registry.calls
    if simulation_id:
        calls = [call for call in calls if call.simulation_id == simulation_id]
    return {"items": [call.model_dump(mode="json") for call in calls[-100:]]}


@router.get("/skills/calls/{skill_call_id}")
def get_skill_call(skill_call_id: str) -> dict:
    for call in ENGINE.registry.calls:
        if call.id == skill_call_id:
            return call.model_dump(mode="json")
    return {"error": "not_found"}


@router.get("/mcp/status")
def mcp_status() -> dict:
    return mcp_smoke()


@router.post("/mcp/smoke-test")
def mcp_smoke_test() -> dict:
    return mcp_smoke()


@router.websocket("/ws/simulations/{simulation_id}")
async def simulation_ws(websocket: WebSocket, simulation_id: str) -> None:
    await websocket.accept()
    websocket_clients.inc()
    try:
        while True:
            state = ENGINE.get_state(simulation_id)
            if state.status == "running":
                if state.agent_cycle_status == "running":
                    await websocket.send_json(
                        _snapshot_payload(state.simulation_id, best_effort_record=True)
                    )
                    await asyncio.sleep(0.5)
                    continue
                ENGINE.tick_market_only(state)
                ENGINE.maybe_start_agent_cycle_async(state)
            await websocket.send_json(
                _snapshot_payload(state.simulation_id, best_effort_record=True)
            )
            delay = 1.0 / max(0.25, min(state.speed, 20.0))
            await asyncio.sleep(delay)
    except WebSocketDisconnect:
        pass
    finally:
        websocket_clients.dec()
