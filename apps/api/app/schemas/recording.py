from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.market import (
    AgentActivityDetail,
    AgentSocietyAdvantageReport,
    SimulationSnapshot,
)

RecordingStatus = Literal["running", "complete", "incomplete", "failed"]


class CreateRecordedSimulationRequest(BaseModel):
    scenario_id: str = "2024-05-10"
    name: str | None = None
    duration_minutes: int = Field(default=60, ge=1, le=480)
    market_data_mode: Literal["synthetic", "yfinance", "alpaca"] | None = None
    real_market_tickers: list[str] = Field(default_factory=list)
    replay_date: str | None = None


class SimulationEstimateRequest(BaseModel):
    scenario_id: str = "2024-05-10"
    duration_minutes: int = Field(default=60, ge=1, le=480)
    market_data_mode: Literal["synthetic", "yfinance", "alpaca"] | None = None
    real_market_tickers: list[str] = Field(default_factory=list)
    replay_date: str | None = None


class SimulationEstimate(BaseModel):
    duration_minutes: int
    expected_agent_cycles: int
    expected_llm_calls: int
    estimated_real_seconds: int
    warning: str


class RecordingManifest(BaseModel):
    recording_id: str
    simulation_id: str
    name: str
    scenario_id: str
    scenario_title: str
    status: RecordingStatus
    duration_minutes: int
    simulated_start: datetime
    simulated_end: datetime | None = None
    created_at: datetime
    updated_at: datetime
    market_data_mode: str = "synthetic"
    tickers: list[str] = Field(default_factory=list)
    frame_count: int = 0
    event_count: int = 0
    last_frame_index: int = -1
    can_continue: bool = True
    summary: str = ""


class SimulationRecordingFrame(BaseModel):
    index: int
    timestamp: datetime
    elapsed_sim_minutes: int
    snapshot: SimulationSnapshot


class SimulationRecordingKeyframe(BaseModel):
    frame_index: int
    event_index: int
    reason: str
    frame: SimulationRecordingFrame


class ReplayBenchmarkPoint(BaseModel):
    frame_index: int
    event_index: int
    reason: str
    timestamp: datetime
    benchmark: AgentSocietyAdvantageReport


class ReplayBenchmarkRun(BaseModel):
    recording_id: str
    scope: Literal["keyframes"] = "keyframes"
    items: list[ReplayBenchmarkPoint] = Field(default_factory=list)
    summary: AgentSocietyAdvantageReport | None = None


class SimulationRecordingFile(BaseModel):
    manifest: RecordingManifest
    frames: list[SimulationRecordingFrame] = Field(default_factory=list)
    activity_details: dict[str, AgentActivityDetail] = Field(default_factory=dict)
    skill_call_details: dict[str, dict[str, Any]] = Field(default_factory=dict)


class RecordedSimulationResponse(BaseModel):
    recording: RecordingManifest
    snapshot: SimulationSnapshot
