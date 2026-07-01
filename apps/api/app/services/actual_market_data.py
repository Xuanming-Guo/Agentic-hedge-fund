from __future__ import annotations

import hashlib
import math
import random
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import httpx

from app.core.config import Settings, has_secret
from app.schemas.market import Instrument, MarketBar, MarketDataMetadata, NewsEvent, Scenario
from app.services.synthetic_data import market_close_for, market_open_for

TICKER_PATTERN = re.compile(r"^[A-Z][A-Z0-9.-]{0,7}$")
DEFAULT_REAL_TICKERS = [
    "AAPL",
    "NVDA",
    "MSFT",
    "TSLA",
    "AMD",
    "AMZN",
    "META",
    "GOOGL",
    "JPM",
    "XOM",
]
SECTOR_BY_TICKER = {
    "AAPL": "Technology",
    "MSFT": "Technology",
    "NVDA": "Technology",
    "AMD": "Technology",
    "TSLA": "Consumer",
    "AMZN": "Consumer",
    "META": "Communication Services",
    "GOOGL": "Communication Services",
    "JPM": "Financials",
    "BAC": "Financials",
    "XOM": "Energy",
    "CVX": "Energy",
    "JNJ": "Healthcare",
    "LLY": "Healthcare",
}
STARTING_PRICE_BY_TICKER = {
    "AAPL": 190.0,
    "NVDA": 125.0,
    "MSFT": 420.0,
    "TSLA": 180.0,
    "AMD": 155.0,
    "AMZN": 185.0,
    "META": 500.0,
    "GOOGL": 175.0,
    "JPM": 200.0,
    "XOM": 115.0,
}


class MarketDataUnavailable(RuntimeError):
    pass


@dataclass(slots=True)
class MarketDataBundle:
    scenario: Scenario
    instruments: list[Instrument]
    bars: list[MarketBar]
    events: list[NewsEvent]
    metadata: MarketDataMetadata


def parse_tickers(raw: str | list[str] | None, *, max_count: int = 10) -> list[str]:
    if raw is None:
        candidates = DEFAULT_REAL_TICKERS
    elif isinstance(raw, str):
        candidates = [item.strip() for item in re.split(r"[\s,]+", raw) if item.strip()]
    else:
        candidates = raw
    tickers: list[str] = []
    for item in candidates:
        symbol = item.strip().upper()
        if not symbol or symbol in tickers:
            continue
        if not TICKER_PATTERN.match(symbol):
            continue
        tickers.append(symbol)
        if len(tickers) >= max_count:
            break
    return tickers or DEFAULT_REAL_TICKERS[:max_count]


def build_real_market_bundle(
    *,
    settings: Settings,
    tickers: list[str] | str | None,
    replay_date: str | None,
    mode: str | None = None,
) -> MarketDataBundle:
    symbols = parse_tickers(tickers or settings.real_market_tickers)
    display_date = replay_date or datetime.now().date().isoformat()
    requested_mode = (mode or settings.market_data_mode or "yfinance").lower()
    if requested_mode not in {"yfinance", "alpaca"}:
        requested_mode = "yfinance"
    try:
        if requested_mode == "alpaca":
            if not has_secret(settings.alpaca_api_key_id) or not has_secret(
                settings.alpaca_api_secret_key
            ):
                raise MarketDataUnavailable("Alpaca credentials are not configured.")
            bars = _fetch_alpaca_bars(
                settings=settings,
                tickers=symbols,
                display_date=display_date,
            )
            provider = "alpaca"
            quote_source = "alpaca_bars"
            feed = settings.alpaca_data_feed
            is_delayed = settings.alpaca_data_feed == "iex"
        else:
            bars, provider, quote_source, feed = _fetch_yfinance_bars(
                settings=settings,
                tickers=symbols,
                display_date=display_date,
            )
            is_delayed = True
        warning = None
        if provider == "yfinance-daily-shaped":
            warning = (
                "using "
                "yfinance daily OHLCV"
            )
    except Exception as exc:
        bars = _generate_fallback_bars(symbols, display_date, str(exc))
        warning = (
            f"Historical {requested_mode} import unavailable; using deterministic generated "
            f"bars for {', '.join(symbols)}. Reason: {str(exc)[:180]}"
        )
        provider = "generated-fallback"
        quote_source = "generated_from_requested_tickers"
        feed = (
            settings.yfinance_interval
            if requested_mode == "yfinance"
            else settings.alpaca_data_feed
        )
        is_delayed = True

    instruments = _instruments_from_bars(symbols, bars)
    scenario = Scenario(
        id=f"actual-{display_date}-{'-'.join(symbols)}",
        display_date=display_date,
        title=f"Actual market replay: {', '.join(symbols)}",
        description=(
            "Imported historical market bars when provider data is available; "
            "limit-order-book depth is generated deterministically for replay."
        ),
        seed=_stable_seed(display_date, ",".join(symbols)),
    )
    metadata = MarketDataMetadata(
        mode=requested_mode,
        provider=provider,
        feed=feed,
        is_delayed=is_delayed,
        quote_source=quote_source,
        depth_source="deterministic_generated_lob_from_bars",
        requested_tickers=symbols,
        active_tickers=[instrument.symbol for instrument in instruments],
        replay_date=display_date,
        warning=warning,
    )
    return MarketDataBundle(
        scenario=scenario,
        instruments=instruments,
        bars=bars,
        events=_events_from_bars(scenario, bars),
        metadata=metadata,
    )


def _fetch_alpaca_bars(
    *,
    settings: Settings,
    tickers: list[str],
    display_date: str,
) -> list[MarketBar]:
    start = market_open_for(display_date)
    end = market_close_for(display_date)
    response = httpx.get(
        f"{settings.alpaca_data_base_url.rstrip('/')}/v2/stocks/bars",
        headers={
            "APCA-API-KEY-ID": settings.alpaca_api_key_id,
            "APCA-API-SECRET-KEY": settings.alpaca_api_secret_key,
        },
        params={
            "symbols": ",".join(tickers),
            "timeframe": "1Min",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "feed": settings.alpaca_data_feed,
            "adjustment": "raw",
            "limit": 10000,
        },
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    bars_by_symbol = payload.get("bars") or {}
    bars: list[MarketBar] = []
    for symbol in tickers:
        for item in bars_by_symbol.get(symbol, []):
            bars.append(
                MarketBar(
                    symbol=symbol,
                    timestamp=datetime.fromisoformat(item["t"].replace("Z", "+00:00")),
                    open=float(item["o"]),
                    high=float(item["h"]),
                    low=float(item["l"]),
                    close=float(item["c"]),
                    volume=int(item.get("v") or 0),
                )
            )
    if not bars:
        raise MarketDataUnavailable("No Alpaca bars were returned for the requested tickers/date.")
    return sorted(bars, key=lambda bar: (bar.timestamp, bar.symbol))


def _fetch_yfinance_bars(
    *,
    settings: Settings,
    tickers: list[str],
    display_date: str,
) -> tuple[list[MarketBar], str, str, str]:
    interval = settings.yfinance_interval.strip() or "1m"
    start = display_date
    end = (datetime.fromisoformat(display_date).date() + timedelta(days=1)).isoformat()
    data = _download_yfinance(tickers=tickers, start=start, end=end, interval=interval)
    bars = _normalize_yfinance_intraday_data(data, tickers, display_date)
    if bars:
        return bars, "yfinance", f"yfinance_{interval}_bars", interval

    daily_data = _download_yfinance(tickers=tickers, start=start, end=end, interval="1d")
    daily_ohlcv = _normalize_yfinance_daily_data(daily_data, tickers)
    if daily_ohlcv:
        return (
            _generate_intraday_from_daily_ohlc(tickers, display_date, daily_ohlcv),
            "yfinance-daily-shaped",
            "yfinance_daily_ohlcv_intraday_shape",
            f"{interval}->1d",
        )
    raise MarketDataUnavailable(
        f"No yfinance bars were returned for {', '.join(tickers)} on {display_date}."
    )


def _download_yfinance(*, tickers: list[str], start: str, end: str, interval: str) -> Any:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise MarketDataUnavailable("The yfinance package is not installed.") from exc
    return yf.download(
        tickers=" ".join(tickers),
        start=start,
        end=end,
        interval=interval,
        group_by="ticker",
        auto_adjust=False,
        prepost=False,
        actions=False,
        progress=False,
        threads=True,
        repair=True,
    )


def _normalize_yfinance_intraday_data(
    data: Any, tickers: list[str], display_date: str
) -> list[MarketBar]:
    if _dataframe_empty(data):
        return []
    open_time = market_open_for(display_date)
    close_time = market_close_for(display_date)
    bars: list[MarketBar] = []
    for symbol in tickers:
        frame = _symbol_frame(data, symbol)
        if _dataframe_empty(frame):
            continue
        for raw_timestamp, row in frame.iterrows():
            timestamp = _coerce_timestamp(raw_timestamp, open_time)
            if timestamp < open_time or timestamp > close_time:
                continue
            bar = _bar_from_row(symbol, timestamp, row)
            if bar is not None:
                bars.append(bar)
    return sorted(bars, key=lambda bar: (bar.timestamp, bar.symbol))


def _normalize_yfinance_daily_data(data: Any, tickers: list[str]) -> dict[str, dict[str, float]]:
    if _dataframe_empty(data):
        return {}
    daily: dict[str, dict[str, float]] = {}
    for symbol in tickers:
        frame = _symbol_frame(data, symbol)
        if _dataframe_empty(frame):
            continue
        for _, row in frame.iterrows():
            values = _ohlcv_from_row(row)
            if values is None:
                continue
            daily[symbol] = values
            break
    return daily


def _generate_intraday_from_daily_ohlc(
    symbols: list[str], display_date: str, daily_ohlcv: dict[str, dict[str, float]]
) -> list[MarketBar]:
    open_time = market_open_for(display_date)
    bars: list[MarketBar] = []
    for symbol in symbols:
        values = daily_ohlcv.get(symbol)
        if not values:
            continue
        rng = random.Random(_stable_seed(display_date, symbol, "daily-shape"))
        day_open = max(1.0, values["open"])
        day_high = max(day_open, values["high"])
        day_low = max(0.01, min(day_open, values["low"]))
        day_close = max(0.01, values["close"])
        daily_volume = max(391, int(values["volume"]))
        previous = day_open
        for minute in range(391):
            timestamp = open_time + timedelta(minutes=minute)
            progress = minute / 390
            path = day_open + (day_close - day_open) * progress
            wave = math.sin(progress * math.pi) * (day_high - day_low) * 0.18
            noise = rng.gauss(0, max(0.01, day_open * 0.0009))
            close = min(day_high, max(day_low, path + wave + noise))
            if minute == 390:
                close = day_close
            high = min(day_high, max(previous, close) + abs(rng.gauss(0, day_open * 0.0005)))
            low = max(day_low, min(previous, close) - abs(rng.gauss(0, day_open * 0.0005)))
            volume_shape = 1.8 if minute < 30 or minute > 360 else 0.85
            volume = max(1, int(daily_volume / 391 * volume_shape * rng.uniform(0.75, 1.25)))
            bars.append(
                MarketBar(
                    symbol=symbol,
                    timestamp=timestamp,
                    open=round(previous, 2),
                    high=round(max(high, previous, close), 2),
                    low=round(min(low, previous, close), 2),
                    close=round(close, 2),
                    volume=volume,
                )
            )
            previous = close
    if not bars:
        raise MarketDataUnavailable(
            "No yfinance daily OHLCV rows could be shaped into replay bars."
        )
    return sorted(bars, key=lambda bar: (bar.timestamp, bar.symbol))


def _generate_fallback_bars(symbols: list[str], display_date: str, reason: str) -> list[MarketBar]:
    _ = reason
    open_time = market_open_for(display_date)
    bars: list[MarketBar] = []
    for symbol in symbols:
        rng = random.Random(_stable_seed(display_date, symbol))
        price = STARTING_PRICE_BY_TICKER.get(symbol, 80 + rng.random() * 180)
        for minute in range(391):
            timestamp = open_time + timedelta(minutes=minute)
            trend = 0.0002 * math.sin((minute + len(symbol) * 17) / 48)
            shock = 0.0012 * math.sin((minute + _stable_seed(symbol, "shock") % 90) / 22)
            noise = rng.gauss(0, 0.0014)
            close = max(1.0, price * (1 + trend + shock + noise))
            high = max(price, close) * (1 + abs(rng.gauss(0.0009, 0.0003)))
            low = min(price, close) * (1 - abs(rng.gauss(0.0009, 0.0003)))
            volume = int((80_000 + rng.randint(0, 45_000)) * (1.4 if minute < 30 else 0.9))
            bars.append(
                MarketBar(
                    symbol=symbol,
                    timestamp=timestamp,
                    open=round(price, 2),
                    high=round(high, 2),
                    low=round(low, 2),
                    close=round(close, 2),
                    volume=max(1_000, volume),
                )
            )
            price = close
    return sorted(bars, key=lambda bar: (bar.timestamp, bar.symbol))


def _instruments_from_bars(symbols: list[str], bars: list[MarketBar]) -> list[Instrument]:
    by_symbol: dict[str, list[MarketBar]] = {symbol: [] for symbol in symbols}
    for bar in bars:
        by_symbol.setdefault(bar.symbol, []).append(bar)
    instruments: list[Instrument] = []
    for symbol in symbols:
        symbol_bars = by_symbol.get(symbol) or []
        first_price = (
            symbol_bars[0].open
            if symbol_bars
            else STARTING_PRICE_BY_TICKER.get(symbol, 100)
        )
        instruments.append(
            Instrument(
                symbol=symbol,
                display_name=symbol,
                sector=SECTOR_BY_TICKER.get(symbol, "Market Data"),
                tick_size=0.01,
                lot_size=1,
                starting_price=round(float(first_price), 2),
            )
        )
    return instruments


def _events_from_bars(scenario: Scenario, bars: list[MarketBar]) -> list[NewsEvent]:
    by_symbol: dict[str, list[MarketBar]] = {}
    for bar in bars:
        by_symbol.setdefault(bar.symbol, []).append(bar)
    events: list[NewsEvent] = []
    event_index = 1
    for offset in (5, 45, 95, 180, 290):
        candidates: list[tuple[float, str, MarketBar, MarketBar]] = []
        for symbol, symbol_bars in by_symbol.items():
            if len(symbol_bars) <= offset:
                continue
            start_bar = symbol_bars[0]
            event_bar = symbol_bars[offset]
            move = (event_bar.close - start_bar.open) / max(0.01, start_bar.open)
            candidates.append((abs(move), symbol, start_bar, event_bar))
        if not candidates:
            continue
        _, symbol, start_bar, event_bar = max(candidates, key=lambda item: item[0])
        move = (event_bar.close - start_bar.open) / max(0.01, start_bar.open)
        sentiment = "bullish" if move > 0.001 else "bearish" if move < -0.001 else "neutral"
        severity = max(1, min(5, int(abs(move) * 250) + 2))
        direction = "higher" if move >= 0 else "lower"
        events.append(
            NewsEvent(
                id=f"{scenario.id}-market-event-{event_index}",
                scenario_id=scenario.id,
                timestamp=event_bar.timestamp,
                event_type="market_microstructure",
                headline=f"{symbol} trades {direction} on elevated intraday activity.",
                body=(
                    f"{symbol} moved {move * 100:.2f}% from the open with "
                    f"latest 1-minute volume of {event_bar.volume:,}."
                ),
                affected_symbols=[symbol],
                affected_sectors=[SECTOR_BY_TICKER.get(symbol, "Market Data")],
                severity=severity,
                sentiment_hint=sentiment,  # type: ignore[arg-type]
            )
        )
        event_index += 1
    return events


def _stable_seed(*parts: str) -> int:
    digest = hashlib.sha256(":".join(parts).encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


def _dataframe_empty(data: Any) -> bool:
    return data is None or bool(getattr(data, "empty", False))


def _symbol_frame(data: Any, symbol: str) -> Any:
    columns = getattr(data, "columns", None)
    if getattr(columns, "nlevels", 1) > 1:
        try:
            return data[symbol]
        except Exception:
            try:
                return data.xs(symbol, axis=1, level=0)
            except Exception:
                try:
                    return data.xs(symbol, axis=1, level=1)
                except Exception:
                    return None
    return data


def _coerce_timestamp(value: Any, reference: datetime) -> datetime:
    if hasattr(value, "to_pydatetime"):
        timestamp = value.to_pydatetime()
    elif isinstance(value, datetime):
        timestamp = value
    else:
        timestamp = datetime.fromisoformat(str(value))
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=reference.tzinfo)
    return timestamp.astimezone(reference.tzinfo)


def _bar_from_row(symbol: str, timestamp: datetime, row: Any) -> MarketBar | None:
    values = _ohlcv_from_row(row)
    if values is None:
        return None
    return MarketBar(
        symbol=symbol,
        timestamp=timestamp,
        open=round(values["open"], 2),
        high=round(values["high"], 2),
        low=round(values["low"], 2),
        close=round(values["close"], 2),
        volume=max(0, int(values["volume"])),
    )


def _ohlcv_from_row(row: Any) -> dict[str, float] | None:
    open_value = _row_number(row, "Open", "open")
    high_value = _row_number(row, "High", "high")
    low_value = _row_number(row, "Low", "low")
    close_value = _row_number(row, "Close", "close")
    volume_value = _row_number(row, "Volume", "volume", default=0)
    if open_value is None or high_value is None or low_value is None or close_value is None:
        return None
    return {
        "open": open_value,
        "high": max(high_value, open_value, close_value),
        "low": min(low_value, open_value, close_value),
        "close": close_value,
        "volume": volume_value or 0,
    }


def _row_number(row: Any, *names: str, default: float | None = None) -> float | None:
    for name in names:
        try:
            value = row.get(name)
        except AttributeError:
            try:
                value = row[name]
            except Exception:
                value = None
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isnan(number):
            continue
        return number
    return default
