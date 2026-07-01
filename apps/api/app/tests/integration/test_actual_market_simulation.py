from __future__ import annotations

from app.core.config import Settings
from app.services import actual_market_data, simulation_engine


def test_actual_market_simulation_uses_requested_tickers(monkeypatch) -> None:
    monkeypatch.setattr(
        actual_market_data,
        "_download_yfinance",
        lambda **_: type("EmptyFrame", (), {"empty": True})(),
    )
    monkeypatch.setattr(
        simulation_engine,
        "get_settings",
        lambda: Settings(
            database_url="sqlite:///:memory:",
            dashscope_api_key="",
            market_data_mode="yfinance",
        ),
    )
    engine = simulation_engine.SimulationEngine()
    state = engine.create_simulation(
        "actual-market",
        market_data_mode="yfinance",
        real_market_tickers=["AAPL", "NVDA"],
        replay_date="2024-05-10",
    )

    snapshot = engine.snapshot(state.simulation_id)

    assert [instrument.symbol for instrument in snapshot.instruments] == ["AAPL", "NVDA"]
    assert snapshot.market_data.provider == "generated-fallback"
    assert {book.symbol for book in snapshot.orderbooks} == {"AAPL", "NVDA"}
    assert all(
        (level.order_count or 0) > 1
        for book in snapshot.orderbooks
        for level in book.bids[:1]
    )
    assert snapshot.released_events == []
