from __future__ import annotations

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
        if seeded_recordings:
            print(f"Seeded {len(seeded_recordings)} bundled replay recording(s).")
    except Exception as exc:
        print(f"Recording fixture seed skipped: {exc}")


if __name__ == "__main__":
    main()
