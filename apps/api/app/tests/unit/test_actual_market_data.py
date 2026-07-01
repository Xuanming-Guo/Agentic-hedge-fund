from __future__ import annotations

from decimal import Decimal

from app.core.config import Settings
from app.services import actual_market_data
from app.services.actual_market_data import build_real_market_bundle, parse_tickers
from app.services.exchange_service import ExchangeService
from app.services.synthetic_data import market_open_for


class _FakeColumns:
    nlevels = 2


class _FakeSymbolFrame:
    def __init__(self, rows):
        self._rows = rows

    @property
    def empty(self) -> bool:
        return len(self._rows) == 0

    def iterrows(self):
        yield from self._rows


class _FakeYFinanceFrame:
    columns = _FakeColumns()

    def __init__(self, rows_by_symbol):
        self._rows_by_symbol = rows_by_symbol

    @property
    def empty(self) -> bool:
        return all(len(rows) == 0 for rows in self._rows_by_symbol.values())

    def __getitem__(self, symbol: str):
        return _FakeSymbolFrame(self._rows_by_symbol.get(symbol, []))


def test_parse_tickers_dedupes_and_limits() -> None:
    assert parse_tickers("aapl, nvda msft tsla amd goog jpm xom meta amzn bac cvx invalid!") == [
        "AAPL",
        "NVDA",
        "MSFT",
        "TSLA",
        "AMD",
        "GOOG",
        "JPM",
        "XOM",
        "META",
        "AMZN",
    ]


def _row(open_price: float, high: float, low: float, close: float, volume: int) -> dict:
    return {
        "Open": open_price,
        "High": high,
        "Low": low,
        "Close": close,
        "Volume": volume,
    }


def test_yfinance_bundle_uses_mocked_intraday_download(monkeypatch) -> None:
    timestamp = market_open_for("2026-06-12")

    def fake_download(*, tickers, start, end, interval):
        assert interval == "1m"
        assert tickers == ["AAPL", "NVDA"]
        return _FakeYFinanceFrame(
            {
                "AAPL": [(timestamp, _row(190.0, 191.0, 189.5, 190.5, 120_000))],
                "NVDA": [(timestamp, _row(125.0, 126.0, 124.0, 125.5, 180_000))],
            }
        )

    monkeypatch.setattr(actual_market_data, "_download_yfinance", fake_download)

    bundle = build_real_market_bundle(
        settings=Settings(market_data_mode="yfinance"),
        tickers=["AAPL", "NVDA"],
        replay_date="2026-06-12",
        mode="yfinance",
    )

    assert bundle.metadata.mode == "yfinance"
    assert bundle.metadata.provider == "yfinance"
    assert bundle.metadata.quote_source == "yfinance_1m_bars"
    assert bundle.metadata.active_tickers == ["AAPL", "NVDA"]
    assert len(bundle.bars) == 2


def test_yfinance_daily_ohlcv_shapes_old_intraday_replay(monkeypatch) -> None:
    timestamp = market_open_for("2024-05-10")

    def fake_download(*, tickers, start, end, interval):
        if interval == "1m":
            return _FakeYFinanceFrame({symbol: [] for symbol in tickers})
        return _FakeYFinanceFrame(
            {
                "AAPL": [(timestamp, _row(190.0, 193.0, 188.0, 192.0, 39_100_000))],
            }
        )

    monkeypatch.setattr(actual_market_data, "_download_yfinance", fake_download)

    bundle = build_real_market_bundle(
        settings=Settings(market_data_mode="yfinance"),
        tickers=["AAPL"],
        replay_date="2024-05-10",
        mode="yfinance",
    )

    assert bundle.metadata.provider == "yfinance-daily-shaped"
    assert bundle.metadata.warning
    assert bundle.bars[0].open == 190.0
    assert bundle.bars[-1].close == 192.0
    assert len(bundle.bars) == 391


def test_real_market_bundle_falls_back_with_requested_tickers(monkeypatch) -> None:
    monkeypatch.setattr(
        actual_market_data,
        "_download_yfinance",
        lambda **_: _FakeYFinanceFrame({}),
    )

    bundle = build_real_market_bundle(
        settings=Settings(market_data_mode="yfinance"),
        tickers=["AAPL", "NVDA"],
        replay_date="2024-05-10",
        mode="yfinance",
    )

    assert bundle.metadata.mode == "yfinance"
    assert bundle.metadata.provider == "generated-fallback"
    assert bundle.metadata.active_tickers == ["AAPL", "NVDA"]
    assert bundle.metadata.warning
    assert {bar.symbol for bar in bundle.bars} == {"AAPL", "NVDA"}
    assert bundle.events


def test_seeded_orderbook_has_multiple_participants_per_level(monkeypatch) -> None:
    monkeypatch.setattr(
        actual_market_data,
        "_download_yfinance",
        lambda **_: _FakeYFinanceFrame({}),
    )
    exchange = ExchangeService()
    timestamp = build_real_market_bundle(
        settings=Settings(market_data_mode="yfinance"),
        tickers=["AAPL"],
        replay_date="2024-05-10",
        mode="yfinance",
    ).bars[0].timestamp
    exchange.seed_liquidity(
        "sim-test",
        "AAPL",
        Decimal("190.00"),
        timestamp,
        volume_hint=120_000,
        volatility_hint=0.002,
    )

    book = exchange.get_orderbook("AAPL", depth=8)

    assert book.bids
    assert book.asks
    assert max(level.order_count or 0 for level in book.bids + book.asks) > 1
    assert any(len(level.participants) > 1 for level in book.bids + book.asks)
