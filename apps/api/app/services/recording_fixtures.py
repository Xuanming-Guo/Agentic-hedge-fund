from __future__ import annotations

import gzip
import os
import shutil
from pathlib import Path

from app.core.config import get_settings
from app.schemas.recording import RecordingManifest

EXAMPLE_FULL_DAY_REPLAY_NAME = "Example Full Day Simulation 11th June 2025"
EXAMPLE_FULL_DAY_REPLAY_SLUG = "example-full-day-simulation-2025-06-11"
FIXTURE_RECORDINGS_DIR = Path(__file__).resolve().parents[1] / "recording_fixtures"


def seed_recording_fixtures(
    *,
    fixture_root: Path | None = None,
    target_root: Path | None = None,
) -> list[str]:
    source_root = fixture_root or FIXTURE_RECORDINGS_DIR
    destination_root = target_root or Path(get_settings().simulation_recordings_dir)
    seeded: list[str] = []

    if not source_root.exists():
        return seeded

    destination_root.mkdir(parents=True, exist_ok=True)

    for manifest_path in sorted(source_root.glob("*/manifest.json")):
        manifest = RecordingManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
        fixture_dir = manifest_path.parent
        target_dir = destination_root / manifest.recording_id
        if _recording_exists(target_dir):
            continue

        temp_dir = destination_root / f".{manifest.recording_id}.tmp"
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        temp_dir.mkdir(parents=True)

        for item in fixture_dir.iterdir():
            if item.name == "frames.ndjson.gz" or item.name.startswith(
                "frames.ndjson.gz.part"
            ):
                continue
            destination = temp_dir / item.name
            if item.is_dir():
                shutil.copytree(item, destination)
            else:
                shutil.copy2(item, destination)

        if not (temp_dir / "frames.ndjson").exists():
            _restore_compressed_frames(fixture_dir, temp_dir)

        _ensure_sidecar(temp_dir / "activity_details.json")
        _ensure_sidecar(temp_dir / "skill_call_details.json")

        if _recording_exists(target_dir):
            shutil.rmtree(temp_dir)
            continue
        if target_dir.exists():
            shutil.rmtree(target_dir)
        os.replace(temp_dir, target_dir)
        seeded.append(manifest.recording_id)

    return seeded


def _recording_exists(recording_dir: Path) -> bool:
    return (
        (recording_dir / "manifest.json").exists()
        and (recording_dir / "frames.ndjson").exists()
    )


def _ensure_sidecar(path: Path) -> None:
    if not path.exists():
        path.write_text("{}", encoding="utf-8")


def _restore_compressed_frames(fixture_dir: Path, temp_dir: Path) -> None:
    compressed_frames = fixture_dir / "frames.ndjson.gz"
    compressed_source = compressed_frames
    assembled_source: Path | None = None

    if not compressed_source.exists():
        frame_parts = sorted(fixture_dir.glob("frames.ndjson.gz.part*"))
        if not frame_parts:
            return
        assembled_source = temp_dir / "frames.ndjson.gz"
        with assembled_source.open("wb") as destination:
            for part in frame_parts:
                with part.open("rb") as source:
                    shutil.copyfileobj(source, destination)
        compressed_source = assembled_source

    try:
        with gzip.open(compressed_source, "rb") as source:
            with (temp_dir / "frames.ndjson").open("wb") as destination:
                shutil.copyfileobj(source, destination)
    finally:
        if assembled_source and assembled_source.exists():
            assembled_source.unlink()
