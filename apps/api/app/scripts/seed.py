from __future__ import annotations

from pathlib import Path

from app.core.config import get_settings
from app.services.recording_fixtures import seed_recording_fixtures
from app.services.synthetic_data import DATASET


def main() -> None:
    try:
        from sqlalchemy.dialects.postgresql import insert

        from app.db.session import SessionLocal
        from app.models.domain import ScenarioModel

        with SessionLocal() as session:
            for scenario in DATASET.scenarios.values():
                stmt = (
                    insert(ScenarioModel)
                    .values(**scenario.model_dump())
                    .on_conflict_do_nothing(index_elements=["id"])
                )
                session.execute(stmt)
            session.commit()
            print(f"Seeded {len(DATASET.scenarios)} scenarios.")
    except Exception as exc:
        # The API can still run in deterministic in-memory mode during local tests.
        print(f"Seed skipped: {exc}")

    try:
        seeded_recordings = seed_recording_fixtures()
        recordings_dir = Path(get_settings().simulation_recordings_dir)
        if seeded_recordings:
            print(
                "Seeded "
                f"{len(seeded_recordings)} bundled replay recording(s) into {recordings_dir}: "
                f"{', '.join(seeded_recordings)}"
            )
        else:
            print(
                "Bundled replay fixture already present or no fixture seed was needed "
                f"in {recordings_dir}."
            )
    except Exception as exc:
        print(f"Recording fixture seed skipped: {exc}")


if __name__ == "__main__":
    main()
