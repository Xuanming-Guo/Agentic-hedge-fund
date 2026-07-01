from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

Side = Literal["buy", "sell"]
OrderType = Literal["market", "limit", "stop", "stop_limit"]
TimeInForce = Literal["DAY", "IOC", "FOK"]
OrderStatus = Literal[
    "open", "partially_filled", "filled", "canceled", "rejected", "expired", "triggered"
]


def round_to_tick(price: Decimal, tick_size: Decimal) -> Decimal:
    ticks = (price / tick_size).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return (ticks * tick_size).quantize(tick_size)


@dataclass(slots=True)
class Order:
    id: str
    simulation_id: str
    symbol: str
    owner_type: str
    owner_id: str
    side: Side
    order_type: OrderType
    quantity: int
    remaining_quantity: int
    limit_price: Decimal | None
    stop_price: Decimal | None
    time_in_force: TimeInForce
    status: OrderStatus
    created_at_seq: int
    client_order_id: str
    parent_order_id: str | None = None
    rationale: str | None = None


@dataclass(slots=True)
class Fill:
    id: str
    symbol: str
    incoming_order_id: str
    resting_order_id: str
    side: Side
    price: Decimal
    quantity: int
    taker_owner_type: str
    maker_owner_type: str


@dataclass(slots=True)
class BookDepth:
    bids: list[tuple[Decimal, int]]
    asks: list[tuple[Decimal, int]]
    last_trade: Decimal | None


@dataclass
class LimitOrderBook:
    symbol: str
    tick_size: Decimal = Decimal("0.01")
    buy_orders: list[Order] = field(default_factory=list)
    sell_orders: list[Order] = field(default_factory=list)
    stop_orders: list[Order] = field(default_factory=list)
    fills: list[Fill] = field(default_factory=list)
    last_trade_price: Decimal | None = None
    _fill_seq: int = 0

    def submit_order(self, order: Order) -> list[Fill]:
        if order.quantity <= 0 or order.remaining_quantity <= 0:
            order.status = "rejected"
            return []
        if order.limit_price is not None:
            order.limit_price = round_to_tick(order.limit_price, self.tick_size)
        if order.stop_price is not None:
            order.stop_price = round_to_tick(order.stop_price, self.tick_size)
        if order.order_type in {"stop", "stop_limit"}:
            order.status = "open"
            self.stop_orders.append(order)
            return []
        if order.time_in_force == "FOK" and not self._can_fill_completely(order):
            order.status = "canceled"
            return []
        fills = self._match_incoming(order)
        if order.remaining_quantity == 0:
            order.status = "filled"
        elif fills:
            order.status = "partially_filled"
        if order.remaining_quantity > 0:
            if order.time_in_force in {"IOC", "FOK"} or order.order_type == "market":
                order.status = "canceled" if not fills else "partially_filled"
                order.remaining_quantity = 0
            elif order.order_type == "limit":
                order.status = "open"
                self._rest(order)
        return fills

    def cancel_order(self, order_id: str) -> bool:
        for book in (self.buy_orders, self.sell_orders, self.stop_orders):
            for order in list(book):
                if order.id == order_id and order.status == "open":
                    order.status = "canceled"
                    book.remove(order)
                    return True
        return False

    def replace_order(self, order_id: str, new_price: Decimal, new_quantity: int) -> bool:
        for book in (self.buy_orders, self.sell_orders):
            for order in book:
                if order.id == order_id and order.status == "open":
                    order.limit_price = round_to_tick(new_price, self.tick_size)
                    order.quantity = new_quantity
                    order.remaining_quantity = new_quantity
                    self._sort_books()
                    return True
        return False

    def trigger_stop_orders(self, last_price: Decimal) -> list[Fill]:
        triggered: list[Order] = []
        for order in list(self.stop_orders):
            if (
                order.side == "buy"
                and order.stop_price is not None
                and last_price >= order.stop_price
            ):
                triggered.append(order)
            if (
                order.side == "sell"
                and order.stop_price is not None
                and last_price <= order.stop_price
            ):
                triggered.append(order)
        all_fills: list[Fill] = []
        for order in triggered:
            self.stop_orders.remove(order)
            order.status = "triggered"
            order.order_type = "market" if order.order_type == "stop" else "limit"
            all_fills.extend(self.submit_order(order))
        return all_fills

    def get_depth(self, depth: int = 10) -> BookDepth:
        bid_levels: dict[Decimal, int] = {}
        ask_levels: dict[Decimal, int] = {}
        for order in self.buy_orders:
            if order.limit_price is not None and order.status == "open":
                bid_levels[order.limit_price] = (
                    bid_levels.get(order.limit_price, 0) + order.remaining_quantity
                )
        for order in self.sell_orders:
            if order.limit_price is not None and order.status == "open":
                ask_levels[order.limit_price] = (
                    ask_levels.get(order.limit_price, 0) + order.remaining_quantity
                )
        bids = sorted(bid_levels.items(), key=lambda item: item[0], reverse=True)[:depth]
        asks = sorted(ask_levels.items(), key=lambda item: item[0])[:depth]
        return BookDepth(bids=bids, asks=asks, last_trade=self.last_trade_price)

    def _opposite_book(self, side: Side) -> list[Order]:
        return self.sell_orders if side == "buy" else self.buy_orders

    def _same_book(self, side: Side) -> list[Order]:
        return self.buy_orders if side == "buy" else self.sell_orders

    def _can_fill_completely(self, order: Order) -> bool:
        needed = order.remaining_quantity
        for resting in self._opposite_book(order.side):
            if resting.status != "open" or resting.limit_price is None:
                continue
            if self._crosses(order, resting):
                needed -= resting.remaining_quantity
                if needed <= 0:
                    return True
        return False

    def _match_incoming(self, order: Order) -> list[Fill]:
        fills: list[Fill] = []
        book = self._opposite_book(order.side)
        self._sort_books()
        while order.remaining_quantity > 0 and book:
            resting = book[0]
            if resting.status != "open" or not self._crosses(order, resting):
                break
            trade_qty = min(order.remaining_quantity, resting.remaining_quantity)
            assert resting.limit_price is not None
            self._fill_seq += 1
            fill = Fill(
                id=f"{self.symbol}-fill-{self._fill_seq}",
                symbol=self.symbol,
                incoming_order_id=order.id,
                resting_order_id=resting.id,
                side=order.side,
                price=resting.limit_price,
                quantity=trade_qty,
                taker_owner_type=order.owner_type,
                maker_owner_type=resting.owner_type,
            )
            order.remaining_quantity -= trade_qty
            resting.remaining_quantity -= trade_qty
            if resting.remaining_quantity == 0:
                resting.status = "filled"
                book.pop(0)
            else:
                resting.status = "partially_filled"
            self.last_trade_price = fill.price
            self.fills.append(fill)
            fills.append(fill)
        return fills

    def _crosses(self, incoming: Order, resting: Order) -> bool:
        if incoming.order_type == "market":
            return True
        if incoming.limit_price is None or resting.limit_price is None:
            return False
        if incoming.side == "buy":
            return incoming.limit_price >= resting.limit_price
        return incoming.limit_price <= resting.limit_price

    def _rest(self, order: Order) -> None:
        self._same_book(order.side).append(order)
        self._sort_books()

    def _sort_books(self) -> None:
        self.buy_orders.sort(
            key=lambda order: (-(order.limit_price or Decimal("0")), order.created_at_seq, order.id)
        )
        self.sell_orders.sort(
            key=lambda order: (
                (order.limit_price or Decimal("999999999")),
                order.created_at_seq,
                order.id,
            )
        )
