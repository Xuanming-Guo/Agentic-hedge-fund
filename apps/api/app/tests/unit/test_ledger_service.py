from __future__ import annotations

from decimal import Decimal

from app.services.ledger_service import PortfolioLedger
from app.services.orderbook import Fill


def _fill(*, side: str, price: str, quantity: int) -> Fill:
    return Fill(
        id=f"fill-{side}-{price}-{quantity}",
        symbol="ECHO",
        incoming_order_id="incoming",
        resting_order_id="resting",
        side=side,  # type: ignore[arg-type]
        price=Decimal(price),
        quantity=quantity,
        taker_owner_type="hedge_fund",
        maker_owner_type="background_market_maker",
    )


def test_short_position_tracks_average_price_and_equity() -> None:
    ledger = PortfolioLedger(initial_cash=Decimal("100000"))

    ledger.apply_fill(_fill(side="sell", price="50", quantity=100))
    state = ledger.state({"ECHO": Decimal("45")}, {"ECHO": "Test"})

    position = state.positions[0]
    assert position.quantity == -100
    assert position.average_price == 50.0
    assert position.unrealized_pnl == 500.0
    assert state.equity == 100499.5


def test_covering_short_realizes_pnl() -> None:
    ledger = PortfolioLedger(initial_cash=Decimal("100000"))

    ledger.apply_fill(_fill(side="sell", price="50", quantity=100))
    ledger.apply_fill(_fill(side="buy", price="45", quantity=100))
    state = ledger.state({"ECHO": Decimal("45")}, {"ECHO": "Test"})

    assert state.positions == []
    assert state.realized_pnl == 499.5
    assert state.equity == 100499.0
