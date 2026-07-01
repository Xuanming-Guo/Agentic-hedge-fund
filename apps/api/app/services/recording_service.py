from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.config import get_settings
from app.schemas.market import AgentActivityDetail, SimulationSnapshot
from app.schemas.recording import (
    RecordingManifest,
    SimulationRecordingFile,
    SimulationRecordingFrame,
    SimulationRecordingKeyframe,
)
from app.services.public_redaction import (
    redact_activity_detail_model,
    redact_frame_dict,
    redact_recording_file_dict,
    redact_snapshot_model,
)


class RecordingNotFoundError(KeyError):
    pass


class RecordingCorruptError(ValueError):
    pass


class RecordingService:
    def __init__(self) -> None:
        self.root = Path(get_settings().simulation_recordings_dir)
        self.active_by_simulation: dict[str, str] = {}
        self._locks: dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()

    def create_recording(
        self,
        *,
        snapshot: SimulationSnapshot,
        duration_minutes: int,
        name: str | None,
    ) -> RecordingManifest:
        now = datetime.now(UTC)
        recording_id = f"rec-{uuid4()}"
        manifest = RecordingManifest(
            recording_id=recording_id,
            simulation_id=snapshot.simulation_id,
            name=name or f"{snapshot.scenario.title} {now.strftime('%Y-%m-%d %H:%M')}",
            scenario_id=snapshot.scenario.id,
            scenario_title=snapshot.scenario.title,
            status="running",
            duration_minutes=duration_minutes,
            simulated_start=snapshot.current_time,
            created_at=now,
            updated_at=now,
            market_data_mode=snapshot.market_data.mode,
            tickers=[instrument.symbol for instrument in snapshot.instruments],
            summary="Recording live simulation frames for exact replay.",
        )
        with self._lock_for(recording_id):
            self._recording_dir(recording_id).mkdir(parents=True, exist_ok=True)
            self._frames_path(recording_id).touch(exist_ok=True)
            self._write_manifest(manifest)
            self._write_json(self._activity_details_path(recording_id), {})
            self._write_json(self._skill_call_details_path(recording_id), {})
        self.active_by_simulation[snapshot.simulation_id] = recording_id
        return manifest

    def list_recordings(self) -> list[RecordingManifest]:
        manifests: list[RecordingManifest] = []
        for path in sorted(self.root.glob("*/manifest.json"), reverse=True):
            try:
                manifests.append(RecordingManifest.model_validate_json(path.read_text()))
            except Exception:
                continue
        return sorted(manifests, key=lambda item: item.updated_at, reverse=True)

    def get_recording(self, recording_id: str) -> SimulationRecordingFile:
        with self._lock_for(recording_id):
            if self._has_sidecar_recording(recording_id):
                return self._load_sidecar_recording(recording_id)
            recording = self._load_legacy_recording(recording_id)
            self._migrate_legacy_recording(recording)
            return recording

    def get_manifest(self, recording_id: str) -> RecordingManifest:
        with self._lock_for(recording_id):
            if self._has_sidecar_recording(recording_id):
                return self._read_manifest(recording_id)
            recording = self._load_legacy_recording(recording_id)
            self._migrate_legacy_recording(recording)
            return recording.manifest

    def get_frames(
        self, recording_id: str, *, offset: int = 0, limit: int = 500
    ) -> list[SimulationRecordingFrame]:
        with self._lock_for(recording_id):
            if self._has_sidecar_recording(recording_id):
                frames: list[SimulationRecordingFrame] = []
                end = max(offset, offset + limit)
                for line_number, line in enumerate(self._iter_frame_lines(recording_id)):
                    index = line_number
                    if index < offset:
                        continue
                    if index >= end:
                        break
                    frames.append(self._parse_frame_line(recording_id, line, line_number))
                return frames
            recording = self._load_legacy_recording(recording_id)
            self._migrate_legacy_recording(recording)
            end = max(offset, offset + limit)
            return recording.frames[offset:end]

    def get_keyframes(self, recording_id: str) -> list[SimulationRecordingKeyframe]:
        with self._lock_for(recording_id):
            keyframes: list[SimulationRecordingKeyframe] = []
            previous: dict[str, Any] | None = None
            latest_frame: SimulationRecordingFrame | None = None

            for frame in self._iter_recording_frames(recording_id):
                current = self._snapshot_signature(frame.snapshot)
                reason = (
                    "Initial frame"
                    if previous is None
                    else self._keyframe_change_reason(previous, current)
                )
                if reason:
                    keyframes.append(
                        SimulationRecordingKeyframe(
                            frame_index=frame.index,
                            event_index=len(keyframes),
                            reason=reason,
                            frame=frame,
                        )
                    )
                previous = current
                latest_frame = frame

            if latest_frame and (
                not keyframes or keyframes[-1].frame_index != latest_frame.index
            ):
                keyframes.append(
                    SimulationRecordingKeyframe(
                        frame_index=latest_frame.index,
                        event_index=len(keyframes),
                        reason="Final frame",
                        frame=latest_frame,
                    )
                )

            return keyframes

    def get_frame(self, recording_id: str, index: int) -> SimulationRecordingFrame:
        if index < 0:
            raise RecordingNotFoundError(f"{recording_id}:{index}")
        frames = self.get_frames(recording_id, offset=index, limit=1)
        if not frames:
            raise RecordingNotFoundError(f"{recording_id}:{index}")
        return frames[0]

    def get_activity_detail(
        self, recording_id: str, activity_id: str
    ) -> AgentActivityDetail:
        with self._lock_for(recording_id):
            if self._has_sidecar_recording(recording_id):
                details = self._read_activity_details(recording_id)
            else:
                recording = self._load_legacy_recording(recording_id)
                self._migrate_legacy_recording(recording)
                details = recording.activity_details
            if activity_id not in details:
                raise RecordingNotFoundError(activity_id)
            return details[activity_id]

    def latest_snapshot(self, recording_id: str) -> SimulationSnapshot:
        with self._lock_for(recording_id):
            if self._has_sidecar_recording(recording_id):
                frame = self._read_last_frame(recording_id)
                if frame is None:
                    raise RecordingNotFoundError(recording_id)
                return frame.snapshot
            recording = self._load_legacy_recording(recording_id)
            self._migrate_legacy_recording(recording)
            if not recording.frames:
                raise RecordingNotFoundError(recording_id)
            return recording.frames[-1].snapshot

    def activity_details(self, recording_id: str) -> dict[str, AgentActivityDetail]:
        with self._lock_for(recording_id):
            if self._has_sidecar_recording(recording_id):
                return dict(self._read_activity_details(recording_id))
            recording = self._load_legacy_recording(recording_id)
            self._migrate_legacy_recording(recording)
            return dict(recording.activity_details)

    def bind_for_resume(self, recording_id: str, simulation_id: str) -> RecordingManifest:
        with self._lock_for(recording_id):
            manifest = self.get_manifest(recording_id)
            now = datetime.now(UTC)
            manifest.simulation_id = simulation_id
            manifest.status = "running"
            manifest.can_continue = True
            manifest.updated_at = now
            self._write_manifest(manifest)
        self.active_by_simulation[simulation_id] = recording_id
        return manifest

    def record_snapshot(
        self,
        snapshot: SimulationSnapshot,
        *,
        activity_details: dict[str, AgentActivityDetail],
        skill_call_details: dict[str, dict[str, Any]],
    ) -> RecordingManifest | None:
        recording_id = self.active_by_simulation.get(snapshot.simulation_id)
        if not recording_id:
            return None
        with self._lock_for(recording_id):
            if not self._has_sidecar_recording(recording_id):
                recording = self._load_legacy_recording(recording_id)
                self._migrate_legacy_recording(recording)
            manifest = self._read_manifest(recording_id)
            frame = SimulationRecordingFrame(
                index=manifest.frame_count,
                timestamp=datetime.now(UTC),
                elapsed_sim_minutes=self._elapsed_minutes(manifest, snapshot),
                snapshot=redact_snapshot_model(snapshot),
            )
            self._append_frame(recording_id, frame)

            persisted_activity_details = self._read_activity_details(recording_id)
            persisted_activity_details.update(
                {
                    activity_id: redact_activity_detail_model(detail)
                    for activity_id, detail in activity_details.items()
                }
            )
            self._write_activity_details(recording_id, persisted_activity_details)

            persisted_skill_details = self._read_skill_call_details(recording_id)
            persisted_skill_details.update(self._redact_skill_call_details(skill_call_details))
            self._write_json(
                self._skill_call_details_path(recording_id),
                persisted_skill_details,
            )

            self._refresh_manifest(manifest, snapshot, manifest.frame_count + 1)
            if self._should_complete(manifest, snapshot):
                manifest.status = "complete"
                manifest.can_continue = False
                manifest.summary = "Completed recorded simulation."
                self.active_by_simulation.pop(snapshot.simulation_id, None)
            self._write_manifest(manifest)
            return manifest

    def will_complete(self, snapshot: SimulationSnapshot) -> bool:
        recording_id = self.active_by_simulation.get(snapshot.simulation_id)
        if not recording_id:
            return False
        with self._lock_for(recording_id):
            if not self._has_sidecar_recording(recording_id):
                recording = self._load_legacy_recording(recording_id)
                self._migrate_legacy_recording(recording)
            manifest = self._read_manifest(recording_id)
            return self._should_complete(manifest, snapshot)

    def stop_recording(
        self, snapshot: SimulationSnapshot, *, complete: bool = False
    ) -> RecordingManifest | None:
        recording_id = self.active_by_simulation.get(snapshot.simulation_id)
        if not recording_id:
            return None
        with self._lock_for(recording_id):
            if not self._has_sidecar_recording(recording_id):
                recording = self._load_legacy_recording(recording_id)
                self._migrate_legacy_recording(recording)
            manifest = self._read_manifest(recording_id)
            self._refresh_manifest(manifest, snapshot, manifest.frame_count)
            manifest.status = "complete" if complete else "incomplete"
            manifest.can_continue = not complete
            manifest.summary = (
                "Completed recorded simulation."
                if complete
                else "Stopped early. Replay is available and the simulation can be continued."
            )
            self.active_by_simulation.pop(snapshot.simulation_id, None)
            self._write_manifest(manifest)
            return manifest

    def _refresh_manifest(
        self,
        manifest: RecordingManifest,
        snapshot: SimulationSnapshot,
        frame_count: int,
    ) -> None:
        manifest.updated_at = datetime.now(UTC)
        manifest.simulated_end = snapshot.current_time
        manifest.frame_count = frame_count
        manifest.event_count = len(snapshot.agent_activity_feed)
        manifest.last_frame_index = frame_count - 1
        manifest.market_data_mode = snapshot.market_data.mode
        manifest.tickers = [instrument.symbol for instrument in snapshot.instruments]

    def _should_complete(
        self, manifest: RecordingManifest, snapshot: SimulationSnapshot
    ) -> bool:
        if snapshot.status == "closed":
            return True
        return self._elapsed_minutes(manifest, snapshot) >= manifest.duration_minutes

    def _elapsed_minutes(
        self, manifest: RecordingManifest, snapshot: SimulationSnapshot
    ) -> int:
        return max(0, int((snapshot.current_time - manifest.simulated_start).total_seconds() // 60))

    def _lock_for(self, recording_id: str) -> threading.RLock:
        with self._locks_guard:
            if recording_id not in self._locks:
                self._locks[recording_id] = threading.RLock()
            return self._locks[recording_id]

    def _recording_dir(self, recording_id: str) -> Path:
        return self.root / recording_id

    def _recording_path(self, recording_id: str) -> Path:
        return self._recording_dir(recording_id) / "recording.json"

    def _manifest_path(self, recording_id: str) -> Path:
        return self._recording_dir(recording_id) / "manifest.json"

    def _frames_path(self, recording_id: str) -> Path:
        return self._recording_dir(recording_id) / "frames.ndjson"

    def _activity_details_path(self, recording_id: str) -> Path:
        return self._recording_dir(recording_id) / "activity_details.json"

    def _skill_call_details_path(self, recording_id: str) -> Path:
        return self._recording_dir(recording_id) / "skill_call_details.json"

    def _has_sidecar_recording(self, recording_id: str) -> bool:
        return (
            self._manifest_path(recording_id).exists()
            and self._frames_path(recording_id).exists()
        )

    def _load_sidecar_recording(self, recording_id: str) -> SimulationRecordingFile:
        return SimulationRecordingFile(
            manifest=self._read_manifest(recording_id),
            frames=self._read_all_frames(recording_id),
            activity_details=self._read_activity_details(recording_id),
            skill_call_details=self._read_skill_call_details(recording_id),
        )

    def _load_legacy_recording(self, recording_id: str) -> SimulationRecordingFile:
        path = self._recording_path(recording_id)
        if not path.exists():
            raise RecordingNotFoundError(recording_id)
        raw = path.read_text(encoding="utf-8")
        try:
            return SimulationRecordingFile.model_validate_json(raw)
        except Exception as direct_error:
            try:
                payload = self._decode_first_json_object(raw)
                return SimulationRecordingFile.model_validate(payload)
            except Exception as repair_error:
                raise RecordingCorruptError(
                    "Saved replay file is corrupted and cannot be loaded."
                ) from repair_error or direct_error

    def _decode_first_json_object(self, raw: str) -> Any:
        stripped = raw.lstrip()
        if not stripped:
            raise RecordingCorruptError("Saved replay file is empty.")
        decoder = json.JSONDecoder()
        payload, _ = decoder.raw_decode(stripped)
        return payload

    def _migrate_legacy_recording(self, recording: SimulationRecordingFile) -> None:
        recording_id = recording.manifest.recording_id
        directory = self._recording_dir(recording_id)
        directory.mkdir(parents=True, exist_ok=True)
        self._write_manifest(recording.manifest)
        self._write_frames(recording_id, recording.frames)
        self._write_activity_details(recording_id, recording.activity_details)
        self._write_json(
            self._skill_call_details_path(recording_id),
            self._redact_skill_call_details(recording.skill_call_details),
        )

    def _read_manifest(self, recording_id: str) -> RecordingManifest:
        try:
            return RecordingManifest.model_validate_json(
                self._manifest_path(recording_id).read_text(encoding="utf-8")
            )
        except FileNotFoundError as exc:
            raise RecordingNotFoundError(recording_id) from exc
        except Exception as exc:
            raise RecordingCorruptError("Saved replay manifest is corrupted.") from exc

    def _write_manifest(self, manifest: RecordingManifest) -> None:
        self._write_json(
            self._manifest_path(manifest.recording_id),
            manifest.model_dump(mode="json"),
        )

    def _iter_frame_lines(self, recording_id: str):
        path = self._frames_path(recording_id)
        if not path.exists():
            raise RecordingNotFoundError(recording_id)
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    yield line

    def _iter_recording_frames(self, recording_id: str):
        if self._has_sidecar_recording(recording_id):
            for line_number, line in enumerate(self._iter_frame_lines(recording_id)):
                yield self._parse_frame_line(recording_id, line, line_number)
            return
        recording = self._load_legacy_recording(recording_id)
        self._migrate_legacy_recording(recording)
        yield from recording.frames

    def _read_all_frames(self, recording_id: str) -> list[SimulationRecordingFrame]:
        return [
            self._parse_frame_line(recording_id, line, line_number)
            for line_number, line in enumerate(self._iter_frame_lines(recording_id))
        ]

    def _read_last_frame(self, recording_id: str) -> SimulationRecordingFrame | None:
        latest_line: str | None = None
        latest_line_number = -1
        for line_number, line in enumerate(self._iter_frame_lines(recording_id)):
            latest_line = line
            latest_line_number = line_number
        if latest_line is None:
            return None
        return self._parse_frame_line(recording_id, latest_line, latest_line_number)

    def _parse_frame_line(
        self, recording_id: str, line: str, line_number: int
    ) -> SimulationRecordingFrame:
        try:
            return SimulationRecordingFrame.model_validate_json(line)
        except Exception as exc:
            raise RecordingCorruptError(
                f"Saved replay frame {line_number} is corrupted for {recording_id}."
            ) from exc

    def _append_frame(self, recording_id: str, frame: SimulationRecordingFrame) -> None:
        payload = redact_frame_dict(frame)
        path = self._frames_path(recording_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, separators=(",", ":")))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

    def _write_frames(
        self, recording_id: str, frames: list[SimulationRecordingFrame]
    ) -> None:
        payload = "\n".join(
            json.dumps(redact_frame_dict(frame), separators=(",", ":")) for frame in frames
        )
        if payload:
            payload += "\n"
        self._write_text(self._frames_path(recording_id), payload)

    def _read_activity_details(self, recording_id: str) -> dict[str, AgentActivityDetail]:
        payload = self._read_json(self._activity_details_path(recording_id), default={})
        try:
            return {
                key: AgentActivityDetail.model_validate(value)
                for key, value in payload.items()
            }
        except Exception as exc:
            raise RecordingCorruptError("Saved replay activity details are corrupted.") from exc

    def _write_activity_details(
        self,
        recording_id: str,
        activity_details: dict[str, AgentActivityDetail],
    ) -> None:
        self._write_json(
            self._activity_details_path(recording_id),
            {
                key: value.model_dump(mode="json")
                for key, value in activity_details.items()
            },
        )

    def _read_skill_call_details(self, recording_id: str) -> dict[str, dict[str, Any]]:
        payload = self._read_json(self._skill_call_details_path(recording_id), default={})
        if not isinstance(payload, dict):
            raise RecordingCorruptError("Saved replay skill-call details are corrupted.")
        return payload

    def _redact_skill_call_details(
        self, skill_call_details: dict[str, dict[str, Any]]
    ) -> dict[str, dict[str, Any]]:
        payload = redact_recording_file_dict(
            {
                "manifest": {},
                "frames": [],
                "activity_details": {},
                "skill_call_details": skill_call_details,
            }
        )
        return payload.get("skill_call_details", {})

    def _snapshot_signature(self, snapshot: SimulationSnapshot) -> dict[str, Any]:
        return {
            "released_events": len(snapshot.released_events),
            "agent_activity": len(snapshot.agent_activity_feed or []),
            "agent_status": snapshot.agent_cycle_status or "idle",
            "active_agent": snapshot.active_agent or "",
            "agent_states": "|".join(
                ":".join(
                    [
                        agent.agent_id,
                        agent.status,
                        agent.last_action,
                        agent.target_symbol or "",
                        agent.decision or "",
                        str(agent.quantity or ""),
                    ]
                )
                for agent in snapshot.agent_states
            ),
            "debate": len(snapshot.debate),
            "decisions": len(snapshot.agent_decisions),
            "committees": len(snapshot.committee_decisions),
            "consensus": len(snapshot.consensus),
            "trades": len(snapshot.trade_tape),
            "positions": self._positions_signature(snapshot),
            "pnl": ":".join(
                [
                    f"{snapshot.portfolio.realized_pnl:.0f}",
                    f"{snapshot.portfolio.unrealized_pnl:.0f}",
                    f"{snapshot.portfolio.gross_exposure:.0f}",
                ]
            ),
            "benchmark": (
                f"{snapshot.benchmark.benchmark_run_id}:{snapshot.benchmark.score:.3f}"
                if snapshot.benchmark
                else "none"
            ),
        }

    def _positions_signature(self, snapshot: SimulationSnapshot) -> str:
        if not snapshot.portfolio.positions:
            return "flat"
        return "|".join(
            sorted(
                f"{position.symbol}:{position.quantity}:{position.market_value:.0f}"
                for position in snapshot.portfolio.positions
            )
        )

    def _keyframe_change_reason(
        self, previous: dict[str, Any], current: dict[str, Any]
    ) -> str | None:
        if current["released_events"] > previous["released_events"]:
            return "Released event"
        if current["agent_activity"] > previous["agent_activity"]:
            return "Agent activity"
        if (
            current["agent_status"] != previous["agent_status"]
            or current["active_agent"] != previous["active_agent"]
        ):
            return "Agent runtime transition"
        if current["agent_states"] != previous["agent_states"]:
            return "Agent state update"
        if current["debate"] > previous["debate"]:
            return "Agent debate"
        if current["decisions"] > previous["decisions"]:
            return "Agent decision"
        if current["committees"] > previous["committees"]:
            return "Committee decision"
        if current["consensus"] > previous["consensus"]:
            return "Consensus update"
        if current["trades"] > previous["trades"]:
            return "Execution fill"
        if (
            current["positions"] != previous["positions"]
            or current["pnl"] != previous["pnl"]
        ):
            return "Portfolio update"
        if current["benchmark"] != previous["benchmark"]:
            return "Benchmark update"
        return None

    def _read_json(self, path: Path, *, default: Any | None = None) -> Any:
        if not path.exists():
            return {} if default is None else default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RecordingCorruptError(f"Saved replay file {path.name} is corrupted.") from exc

    def _write_json(self, path: Path, payload: Any) -> None:
        self._write_text(path, json.dumps(payload, indent=2))

    def _write_text(self, path: Path, payload: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f".{path.name}.{uuid4()}.tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)


RECORDINGS = RecordingService()
