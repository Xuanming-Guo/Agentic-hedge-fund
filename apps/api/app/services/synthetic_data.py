from __future__ import annotations

import math
import random
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.schemas.market import Instrument, MarketBar, NewsEvent, Scenario

MARKET_TZ = ZoneInfo("America/New_York")
SYMBOLS = ["ALPH", "BRAV", "CYGN", "DLTN", "ECHO"]

INSTRUMENTS: list[Instrument] = [
    Instrument(
        symbol="ALPH",
        display_name="Alpha Systems",
        sector="Technology",
        tick_size=0.01,
        lot_size=1,
        starting_price=120,
    ),
    Instrument(
        symbol="BRAV",
        display_name="Bravo Retail",
        sector="Consumer",
        tick_size=0.01,
        lot_size=1,
        starting_price=45,
    ),
    Instrument(
        symbol="CYGN",
        display_name="Cygnus Bio",
        sector="Healthcare",
        tick_size=0.01,
        lot_size=1,
        starting_price=80,
    ),
    Instrument(
        symbol="DLTN",
        display_name="Dalton Energy",
        sector="Energy",
        tick_size=0.01,
        lot_size=1,
        starting_price=62,
    ),
    Instrument(
        symbol="ECHO",
        display_name="Echo Financial",
        sector="Financials",
        tick_size=0.01,
        lot_size=1,
        starting_price=35,
    ),
]

SCENARIOS: list[Scenario] = [
    Scenario(
        id="2024-05-10",
        display_date="2024-05-10",
        title="Mixed earnings day with a surprise guidance cut",
        description=(
            "A risk-off open meets idiosyncratic ALPH strength and late financial-sector concern."
        ),
        seed=51024,
    ),
    Scenario(
        id="2024-08-14",
        display_date="2024-08-14",
        title="Macro inflation shock day",
        description=(
            "Hot inflation forces agents to weigh rate-sensitive pressure "
            "against resilient technology demand."
        ),
        seed=81424,
    ),
    Scenario(
        id="2025-02-07",
        display_date="2025-02-07",
        title="Sector rotation day",
        description="Capital rotates out of defensive healthcare into cyclicals and technology.",
        seed=20725,
    ),
    Scenario(
        id="2025-04-03",
        display_date="2025-04-03",
        title="Supply-chain disruption day",
        description="Energy logistics disruption raises volatility and execution risk.",
        seed=40325,
    ),
    Scenario(
        id="2025-09-18",
        display_date="2025-09-18",
        title="AI chip rally and regulatory concern day",
        description=(
            "Technology optimism competes with compliance concern around healthcare headlines."
        ),
        seed=91825,
    ),
]


def market_open_for(display_date: str) -> datetime:
    year, month, day = [int(part) for part in display_date.split("-")]
    return datetime.combine(datetime(year, month, day).date(), time(9, 30), tzinfo=MARKET_TZ)


def premarket_for(display_date: str) -> datetime:
    year, month, day = [int(part) for part in display_date.split("-")]
    return datetime.combine(datetime(year, month, day).date(), time(9, 25), tzinfo=MARKET_TZ)


def market_close_for(display_date: str) -> datetime:
    year, month, day = [int(part) for part in display_date.split("-")]
    return datetime.combine(datetime(year, month, day).date(), time(16, 0), tzinfo=MARKET_TZ)


def generate_events(scenario: Scenario) -> list[NewsEvent]:
    open_time = market_open_for(scenario.display_date)
    specs = [
        (
            5,
            "macro",
            "Inflation print comes in hotter than expected; rate-sensitive sectors weaken.",
            "The market opens risk-off as investors price a higher-for-longer rate path.",
            ["ECHO", "BRAV"],
            ["Financials", "Consumer"],
            4,
            "bearish",
        ),
        (
            45,
            "company_news",
            "ALPH announces stronger-than-expected cloud infrastructure demand.",
            "Alpha Systems reports enterprise cloud bookings above plan despite the macro tape.",
            ["ALPH"],
            ["Technology"],
            4,
            "bullish",
        ),
        (
            95,
            "analyst_rating",
            "Broker desk downgrades BRAV on margin compression concerns.",
            "A sell-side note flags promotional pressure and freight costs for Bravo Retail.",
            ["BRAV"],
            ["Consumer"],
            3,
            "bearish",
        ),
        (
            220,
            "legal_regulatory",
            "CYGN receives regulatory request for additional trial data.",
            "Cygnus Bio says regulators requested more safety data before the next review window.",
            ["CYGN"],
            ["Healthcare"],
            4,
            "bearish",
        ),
        (
            290,
            "supply_chain",
            "DLTN reports temporary refinery disruption but says full-year output remains intact.",
            "Dalton Energy warns of a short outage, while management maintains full-year guidance.",
            ["DLTN"],
            ["Energy"],
            3,
            "mixed",
        ),
        (
            340,
            "rumor",
            "Unconfirmed chatter suggests ECHO has exposure to stressed commercial loans.",
            "The rumor is unverified; compliance flags it as low-evidence unless corroborated.",
            ["ECHO"],
            ["Financials"],
            4,
            "bearish",
        ),
    ]
    return [
        NewsEvent(
            id=f"{scenario.id}-event-{idx + 1}",
            scenario_id=scenario.id,
            timestamp=open_time + timedelta(minutes=offset),
            event_type=event_type,
            headline=headline,
            body=body,
            affected_symbols=symbols,
            affected_sectors=sectors,
            severity=severity,
            sentiment_hint=sentiment,
        )
        for idx, (
            offset,
            event_type,
            headline,
            body,
            symbols,
            sectors,
            severity,
            sentiment,
        ) in enumerate(specs)
    ]


def _event_drift(symbol: str, minute: int, events: list[NewsEvent]) -> float:
    drift = 0.0
    for event in events:
        event_minute = (
            int((event.timestamp - market_open_for(event.scenario_id)).total_seconds() // 60)
            if False
            else None
        )
        _ = event_minute
        # Synthetic event effects are keyed by event id order for deterministic readability.
        if symbol in event.affected_symbols:
            sign = (
                1.0
                if event.sentiment_hint == "bullish"
                else -1.0
                if event.sentiment_hint == "bearish"
                else 0.15
            )
            event_offset = {
                "event-1": 5,
                "event-2": 45,
                "event-3": 95,
                "event-4": 220,
                "event-5": 290,
                "event-6": 340,
            }
            key = next((name for name in event_offset if event.id.endswith(name)), "")
            distance = max(0, minute - event_offset.get(key, 999))
            if 0 <= distance <= 70:
                drift += sign * event.severity * 0.00016 * math.exp(-distance / 55)
    return drift


def generate_bars(scenario: Scenario) -> list[MarketBar]:
    rng = random.Random(scenario.seed)
    open_time = market_open_for(scenario.display_date)
    events = generate_events(scenario)
    bars: list[MarketBar] = []
    prices = {instrument.symbol: float(instrument.starting_price) for instrument in INSTRUMENTS}
    for minute in range(391):
        timestamp = open_time + timedelta(minutes=minute)
        volume_shape = (
            1.4 if minute < 30 or minute > 360 else 0.8 + 0.3 * math.sin(minute / 391 * math.pi)
        )
        for instrument in INSTRUMENTS:
            symbol = instrument.symbol
            previous = prices[symbol]
            macro = -0.00018 if minute >= 5 and symbol in {"BRAV", "ECHO"} else 0.0
            symbol_drift = _event_drift(symbol, minute, events)
            seasonal = 0.00005 * math.sin((minute + len(symbol) * 11) / 38)
            noise = rng.gauss(0, 0.0016)
            close = max(1.0, previous * (1 + macro + symbol_drift + seasonal + noise))
            high = max(previous, close) * (1 + abs(rng.gauss(0.0008, 0.0004)))
            low = min(previous, close) * (1 - abs(rng.gauss(0.0008, 0.0004)))
            volume = int(
                (18_000 + rng.randint(0, 8_000)) * volume_shape * (1 + abs(symbol_drift) * 800)
            )
            bars.append(
                MarketBar(
                    symbol=symbol,
                    timestamp=timestamp,
                    open=round(previous, 2),
                    high=round(high, 2),
                    low=round(low, 2),
                    close=round(close, 2),
                    volume=max(1_000, volume),
                )
            )
            prices[symbol] = close
    return bars


class SyntheticDataset:
    def __init__(self) -> None:
        self.scenarios = {scenario.id: scenario for scenario in SCENARIOS}
        self.instruments = {instrument.symbol: instrument for instrument in INSTRUMENTS}
        self.events = {scenario.id: generate_events(scenario) for scenario in SCENARIOS}
        self.bars = {scenario.id: generate_bars(scenario) for scenario in SCENARIOS}


DATASET = SyntheticDataset()
