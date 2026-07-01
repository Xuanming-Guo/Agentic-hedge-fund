from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime

from app.services.recording_fixtures import (
    EXAMPLE_FULL_DAY_REPLAY_NAME,
    EXAMPLE_FULL_DAY_REPLAY_SLUG,
    seed_recording_fixtures,
)


def _manifest(recording_id: str) -> dict:
    now = datetime(2025, 6, 11, 15, 30, tzinfo=UTC).isoformat()
    return {
        "recording_id": recording_id,
        "simulation_id": "sim-example",
        "name": EXAMPLE_FULL_DAY_REPLAY_NAME,
        "scenario_id": "actual-market",
        "scenario_title": "Actual market data",
        "status": "complete",
        "duration_minutes": 390,
        "simulated_start": now,
        "simulated_end": now,
        "created_at": now,
        "updated_at": now,
        "market_data_mode": "yfinance",
        "tickers": ["AAPL", "NVDA", "MSFT", "TSLA", "AMD"],
        "frame_count": 1,
        "event_count": 1,
        "last_frame_index": 0,
        "can_continue": False,
        "summary": "Curated full-day replay fixture.",
    }


def test_seed_recording_fixtures_copies_bundled_replay(tmp_path) -> None:
    fixture_root = tmp_path / "fixtures"
    fixture_dir = fixture_root / EXAMPLE_FULL_DAY_REPLAY_SLUG
    target_root = tmp_path / "recordings"
    fixture_dir.mkdir(parents=True)
    manifest = _manifest("rec-example-full-day-2025-06-11")
    (fixture_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (fixture_dir / "frames.ndjson").write_text("{}\n", encoding="utf-8")

    seeded = seed_recording_fixtures(fixture_root=fixture_root, target_root=target_root)

    target_dir = target_root / manifest["recording_id"]
    assert seeded == [manifest["recording_id"]]
    assert json.loads((target_dir / "manifest.json").read_text())["name"] == (
        EXAMPLE_FULL_DAY_REPLAY_NAME
    )
    assert (target_dir / "frames.ndjson").read_text() == "{}\n"
    assert json.loads((target_dir / "activity_details.json").read_text()) == {}
    assert json.loads((target_dir / "skill_call_details.json").read_text()) == {}


def test_seed_recording_fixtures_reconstructs_gzipped_frames(tmp_path) -> None:
    fixture_root = tmp_path / "fixtures"
    fixture_dir = fixture_root / EXAMPLE_FULL_DAY_REPLAY_SLUG
    target_root = tmp_path / "recordings"
    fixture_dir.mkdir(parents=True)
    manifest = _manifest("rec-gzipped-example")
    (fixture_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with gzip.open(fixture_dir / "frames.ndjson.gz", "wb") as handle:
        handle.write(b"{\"index\":0}\n")

    seeded = seed_recording_fixtures(fixture_root=fixture_root, target_root=target_root)

    assert seeded == [manifest["recording_id"]]
    assert (target_root / manifest["recording_id"] / "frames.ndjson").read_text() == (
        '{"index":0}\n'
    )


def test_seed_recording_fixtures_reconstructs_chunked_gzip_frames(tmp_path) -> None:
    fixture_root = tmp_path / "fixtures"
    fixture_dir = fixture_root / EXAMPLE_FULL_DAY_REPLAY_SLUG
    target_root = tmp_path / "recordings"
    fixture_dir.mkdir(parents=True)
    manifest = _manifest("rec-chunked-example")
    (fixture_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    compressed = gzip.compress(b'{"index":0}\n{"index":1}\n')
    midpoint = len(compressed) // 2
    (fixture_dir / "frames.ndjson.gz.part001").write_bytes(compressed[:midpoint])
    (fixture_dir / "frames.ndjson.gz.part002").write_bytes(compressed[midpoint:])

    seeded = seed_recording_fixtures(fixture_root=fixture_root, target_root=target_root)

    assert seeded == [manifest["recording_id"]]
    assert (target_root / manifest["recording_id"] / "frames.ndjson").read_text() == (
        '{"index":0}\n{"index":1}\n'
    )
