from __future__ import annotations

from datetime import datetime

from app.schemas.market import MarketBar, NewsEvent


class FutureDataFirewall:
    def visible_bars(self, bars: list[MarketBar], timestamp: datetime) -> list[MarketBar]:
        return [bar for bar in bars if bar.timestamp <= timestamp]

    def visible_events(self, events: list[NewsEvent], timestamp: datetime) -> list[NewsEvent]:
        return [event for event in events if event.timestamp <= timestamp and event.public]

    def assert_point_in_time(
        self, current_time: datetime, requested_data_timestamp: datetime
    ) -> None:
        if requested_data_timestamp > current_time:
            raise ValueError("Future data access blocked by FutureDataFirewall.")

    def inspect_text(self, text: str) -> tuple[bool, list[str]]:
        suspected = [
            term
            for term in ("future return", "tomorrow close", "hidden label", "realized movement")
            if term in text.lower()
        ]
        return (not suspected, suspected)
