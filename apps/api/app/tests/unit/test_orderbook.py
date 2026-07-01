from __future__ import annotations

from decimal import Decimal

from app.services.orderbook import LimitOrderBook, Order


def make_order(
    order_id: str,
    side: str,
    price: str | None,
    qty: int,
    seq: int,
    order_type: str = "limit",
    tif: str = "DAY",
    stop: str | None = None,
) -> Order:
    return Order(
        id=order_id,
        simulation_id="sim",
        symbol="ALPH",
        owner_type="hedge_fund" if order_id.startswith("hf") else "background_market_maker",
        owner_id="owner",
        side=side,  # type: ignore[arg-type]
        order_type=order_type,  # type: ignore[arg-type]
        quantity=qty,
        remaining_quantity=qty,
        limit_price=Decimal(price) if price else None,
        stop_price=Decimal(stop) if stop else None,
        time_in_force=tif,  # type: ignore[arg-type]
        status="open",
        created_at_seq=seq,
        client_order_id=order_id,
    )


def test_price_time_priority() -> None:
    book = LimitOrderBook("ALPH")
    book.submit_order(make_order("ask-2", "sell", "10.00", 100, 2))
    book.submit_order(make_order("ask-1", "sell", "10.00", 100, 1))
    fills = book.submit_order(make_order("hf-buy", "buy", None, 100, 3, "market"))
    assert fills[0].resting_order_id == "ask-1"


def test_market_order_sweeps_multiple_levels() -> None:
    book = LimitOrderBook("ALPH")
    book.submit_order(make_order("ask-1", "sell", "10.00", 100, 1))
    book.submit_order(make_order("ask-2", "sell", "10.05", 100, 2))
    fills = book.submit_order(make_order("hf-buy", "buy", None, 150, 3, "market"))
    assert [fill.quantity for fill in fills] == [100, 50]
    assert fills[-1].price == Decimal("10.05")


def test_limit_order_rests_when_not_crossing() -> None:
    book = LimitOrderBook("ALPH")
    book.submit_order(make_order("bid-1", "buy", "9.90", 100, 1))
    depth = book.get_depth()
    assert depth.bids[0] == (Decimal("9.90"), 100)


def test_crossing_limit_fills_immediately() -> None:
    book = LimitOrderBook("ALPH")
    book.submit_order(make_order("ask-1", "sell", "10.00", 100, 1))
    fills = book.submit_order(make_order("hf-buy", "buy", "10.00", 100, 2))
    assert len(fills) == 1
    assert fills[0].price == Decimal("10.00")


def test_partial_fill_and_ioc_cancellation() -> None:
    book = LimitOrderBook("ALPH")
    book.submit_order(make_order("ask-1", "sell", "10.00", 50, 1))
    order = make_order("hf-buy", "buy", "10.00", 100, 2, "limit", "IOC")
    fills = book.submit_order(order)
    assert fills[0].quantity == 50
    assert order.remaining_quantity == 0
    assert order.status == "partially_filled"


def test_fok_full_or_cancel() -> None:
    book = LimitOrderBook("ALPH")
    book.submit_order(make_order("ask-1", "sell", "10.00", 50, 1))
    order = make_order("hf-buy", "buy", "10.00", 100, 2, "limit", "FOK")
    fills = book.submit_order(order)
    assert fills == []
    assert order.status == "canceled"


def test_stop_order_trigger() -> None:
    book = LimitOrderBook("ALPH")
    book.submit_order(make_order("ask-1", "sell", "10.10", 100, 1))
    stop = make_order("hf-stop", "buy", None, 50, 2, "stop", "DAY", "10.05")
    book.submit_order(stop)
    fills = book.trigger_stop_orders(Decimal("10.05"))
    assert fills[0].incoming_order_id == "hf-stop"


def test_stop_limit_order_trigger() -> None:
    book = LimitOrderBook("ALPH")
    book.submit_order(make_order("ask-1", "sell", "10.10", 100, 1))
    stop = make_order("hf-stop-limit", "buy", "10.10", 50, 2, "stop_limit", "DAY", "10.05")
    book.submit_order(stop)
    fills = book.trigger_stop_orders(Decimal("10.05"))
    assert len(fills) == 1


def test_cancel_order() -> None:
    book = LimitOrderBook("ALPH")
    book.submit_order(make_order("bid-1", "buy", "9.90", 100, 1))
    assert book.cancel_order("bid-1")
    assert book.get_depth().bids == []


def test_deterministic_result_same_sequence() -> None:
    def run() -> list[str]:
        book = LimitOrderBook("ALPH")
        book.submit_order(make_order("ask-1", "sell", "10.00", 100, 1))
        book.submit_order(make_order("ask-2", "sell", "10.05", 100, 2))
        return [
            fill.id
            for fill in book.submit_order(make_order("hf-buy", "buy", None, 120, 3, "market"))
        ]

    assert run() == run()
