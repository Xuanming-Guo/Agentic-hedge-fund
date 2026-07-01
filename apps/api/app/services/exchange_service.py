from __future__ import annotations

import random
from dataclasses import dataclass, field
from decimal import Decimal

from app.schemas.market import (
    OrderBookLevel,
    OrderBookParticipant,
    OrderBookSnapshot,
    TradeTapeItem,
)
from app.services.orderbook import Fill, LimitOrderBook, Order


@dataclass
class ExchangeService:
    books: dict[str, LimitOrderBook] = field(default_factory=dict)
    sequence: int = 0
    tape: list[TradeTapeItem] = field(default_factory=list)

    def get_book(self, symbol: str) -> LimitOrderBook:
        if symbol not in self.books:
            self.books[symbol] = LimitOrderBook(symbol=symbol)
        return self.books[symbol]

    def seed_liquidity(
        self,
        simulation_id: str,
        symbol: str,
        mid: Decimal,
        timestamp,
        *,
        volume_hint: int = 0,
        volatility_hint: float = 0.0,
    ) -> None:
        book = self.get_book(symbol)
        book.buy_orders = [order for order in book.buy_orders if order.owner_type == "hedge_fund"]
        book.sell_orders = [order for order in book.sell_orders if order.owner_type == "hedge_fund"]
        rng = random.Random(f"{simulation_id}:{symbol}:{timestamp.isoformat()}:{mid}")
        spread_multiplier = Decimal(str(0.00055 + min(0.004, volatility_hint * 0.08)))
        spread = max(Decimal("0.02"), mid * spread_multiplier)
        liquidity_scale = max(160, min(5000, int(160 + volume_hint / 180)))
        participants = [
            ("background_market_maker", 0.58),
            ("institutional_liquidity", 0.24),
            ("retail_lot", 0.12),
            ("dark_pool_proxy", 0.06),
        ]
        for level in range(1, 9):
            total_size = int(liquidity_scale * (0.75 + level * 0.16) * rng.uniform(0.82, 1.2))
            bid = mid - spread / Decimal("2") - Decimal(level - 1) * Decimal("0.03")
            ask = mid + spread / Decimal("2") + Decimal(level - 1) * Decimal("0.03")
            for side, price in (("buy", bid), ("sell", ask)):
                remaining = total_size
                for index, (owner_type, share) in enumerate(participants):
                    order_count = 1 + rng.randint(0, 2 if owner_type != "retail_lot" else 5)
                    participant_qty = (
                        remaining
                        if index == len(participants) - 1
                        else max(1, int(total_size * share * rng.uniform(0.75, 1.25)))
                    )
                    remaining = max(0, remaining - participant_qty)
                    child_remaining = participant_qty
                    for child_index in range(order_count):
                        child_qty = (
                            child_remaining
                            if child_index == order_count - 1
                            else max(1, child_remaining // (order_count - child_index))
                        )
                        child_remaining = max(0, child_remaining - child_qty)
                        self.sequence += 1
                        book.submit_order(
                            Order(
                                id=f"liq-{symbol}-{side}-{level}-{self.sequence}",
                                simulation_id=simulation_id,
                                symbol=symbol,
                                owner_type=owner_type,
                                owner_id=owner_type,
                                side=side,  # type: ignore[arg-type]
                                order_type="limit",
                                quantity=child_qty,
                                remaining_quantity=child_qty,
                                limit_price=price,
                                stop_price=None,
                                time_in_force="DAY",
                                status="open",
                                created_at_seq=self.sequence,
                                client_order_id=f"liq-{side}-{self.sequence}",
                            )
                        )

    def submit_order(self, order: Order, timestamp) -> list[Fill]:
        fills = self.get_book(order.symbol).submit_order(order)
        for fill in fills:
            self.tape.append(
                TradeTapeItem(
                    id=fill.id,
                    timestamp=timestamp,
                    symbol=fill.symbol,
                    side=fill.side,
                    price=float(fill.price),
                    quantity=fill.quantity,
                    owner_type=fill.taker_owner_type,
                )
            )
        return fills

    def get_orderbook(self, symbol: str, depth: int = 10) -> OrderBookSnapshot:
        book = self.get_book(symbol)
        depth_view = book.get_depth(depth)
        bid_price = depth_view.bids[0][0] if depth_view.bids else Decimal("0")
        ask_price = depth_view.asks[0][0] if depth_view.asks else Decimal("0")
        mid = (
            (bid_price + ask_price) / Decimal("2")
            if bid_price and ask_price
            else bid_price or ask_price
        )
        spread = ask_price - bid_price if bid_price and ask_price else Decimal("0")
        bid_qty = sum(quantity for _, quantity in depth_view.bids)
        ask_qty = sum(quantity for _, quantity in depth_view.asks)
        imbalance = (bid_qty - ask_qty) / max(1, bid_qty + ask_qty)
        return OrderBookSnapshot(
            symbol=symbol,
            bids=[
                OrderBookLevel(
                    price=float(price),
                    quantity=quantity,
                    order_count=self._order_count_at_level(book, "buy", price),
                    participants=self._participants_at_level(book, "buy", price),
                )
                for price, quantity in depth_view.bids
            ],
            asks=[
                OrderBookLevel(
                    price=float(price),
                    quantity=quantity,
                    order_count=self._order_count_at_level(book, "sell", price),
                    participants=self._participants_at_level(book, "sell", price),
                )
                for price, quantity in depth_view.asks
            ],
            mid=float(mid),
            spread=float(spread),
            imbalance=round(imbalance, 3),
            last_trade=float(depth_view.last_trade) if depth_view.last_trade else None,
        )

    def recent_tape(self, symbol: str | None = None, limit: int = 100) -> list[TradeTapeItem]:
        items = [item for item in self.tape if symbol is None or item.symbol == symbol]
        return items[-limit:]

    def _orders_at_level(
        self, book: LimitOrderBook, side: str, price: Decimal
    ) -> list[Order]:
        orders = book.buy_orders if side == "buy" else book.sell_orders
        return [
            order
            for order in orders
            if order.status == "open"
            and order.limit_price == price
            and order.remaining_quantity > 0
        ]

    def _order_count_at_level(
        self, book: LimitOrderBook, side: str, price: Decimal
    ) -> int:
        return len(self._orders_at_level(book, side, price))

    def _participants_at_level(
        self, book: LimitOrderBook, side: str, price: Decimal
    ) -> list[OrderBookParticipant]:
        grouped: dict[str, dict[str, int]] = {}
        for order in self._orders_at_level(book, side, price):
            participant = grouped.setdefault(order.owner_type, {"order_count": 0, "quantity": 0})
            participant["order_count"] += 1
            participant["quantity"] += order.remaining_quantity
        return [
            OrderBookParticipant(
                owner_type=owner_type,
                order_count=values["order_count"],
                quantity=values["quantity"],
            )
            for owner_type, values in sorted(grouped.items())
        ]
