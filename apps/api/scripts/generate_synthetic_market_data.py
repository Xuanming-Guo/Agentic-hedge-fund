from __future__ import annotations

import json

from app.services.synthetic_data import DATASET


def main() -> None:
    payload = {
        "scenarios": [scenario.model_dump(mode="json") for scenario in DATASET.scenarios.values()],
        "events": {key: [event.model_dump(mode="json") for event in value] for key, value in DATASET.events.items()},
        "bars_preview": {key: [bar.model_dump(mode="json") for bar in value[:10]] for key, value in DATASET.bars.items()},
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
