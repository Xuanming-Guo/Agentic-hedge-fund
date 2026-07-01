from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.schemas.market import PortfolioState, Position
from app.services.orderbook import Fill
from app.services.synthetic_data import INSTRUMENTS


@dataclass(slots=True)
class LedgerPosition:
    symbol: str
    quantity: int = 0
    average_price: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")


@dataclass
class PortfolioLedger:
    initial_cash: Decimal = Decimal("1000000")
    commission_per_share: Decimal = Decimal("0.005")
    positions: dict[str, LedgerPosition] = field(default_factory=dict)
    cash: Decimal = Decimal("1000000")
    realized_pnl: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        self.cash = self.initial_cash
        self.positions = {
            instrument.symbol: LedgerPosition(symbol=instrument.symbol)
            for instrument in INSTRUMENTS
        }

    def ensure_symbol(self, symbol: str) -> None:
        self.positions.setdefault(symbol, LedgerPosition(symbol=symbol))

    def apply_fill(self, fill: Fill, hedge_fund_is_taker: bool = True) -> None:
        if fill.taker_owner_type != "hedge_fund" and fill.maker_owner_type != "hedge_fund":
            return
        self.ensure_symbol(fill.symbol)
        position = self.positions[fill.symbol]
        signed_qty = (
            fill.quantity
            if fill.side == "buy" and fill.taker_owner_type == "hedge_fund"
            else -fill.quantity
        )
        if fill.maker_owner_type == "hedge_fund":
            signed_qty = -fill.quantity if fill.side == "buy" else fill.quantity
        notional = fill.price * Decimal(fill.quantity)
        fee = self.commission_per_share * Decimal(fill.quantity)
        if signed_qty > 0:
            self.cash -= notional + fee
            if position.quantity < 0:
                cover_qty = min(signed_qty, abs(position.quantity))
                realized = (position.average_price - fill.price) * Decimal(cover_qty)
                position.realized_pnl += realized - fee
                self.realized_pnl += realized - fee
                position.quantity += cover_qty
                remaining_qty = signed_qty - cover_qty
                if remaining_qty > 0:
                    position.quantity = remaining_qty
                    position.average_price = fill.price
                elif position.quantity == 0:
                    position.average_price = Decimal("0")
            else:
                total_cost = position.average_price * Decimal(position.quantity) + notional
                position.quantity += signed_qty
                position.average_price = total_cost / Decimal(position.quantity)
        else:
            sell_qty = abs(signed_qty)
            self.cash += notional - fee
            if position.quantity > 0:
                close_qty = min(sell_qty, position.quantity)
                realized = (fill.price - position.average_price) * Decimal(close_qty)
                position.realized_pnl += realized - fee
                self.realized_pnl += realized - fee
                position.quantity -= close_qty
                remaining_qty = sell_qty - close_qty
                if remaining_qty > 0:
                    position.quantity = -remaining_qty
                    position.average_price = fill.price
                elif position.quantity == 0:
                    position.average_price = Decimal("0")
            else:
                current_short = abs(position.quantity)
                total_proceeds = position.average_price * Decimal(current_short) + notional
                position.quantity -= sell_qty
                position.average_price = total_proceeds / Decimal(abs(position.quantity))

    def state(
        self, latest_prices: dict[str, Decimal], sector_map: dict[str, str]
    ) -> PortfolioState:
        positions: list[Position] = []
        unrealized = Decimal("0")
        gross = Decimal("0")
        net = Decimal("0")
        sector_exposure: dict[str, Decimal] = {}
        for symbol, position in self.positions.items():
            price = latest_prices.get(symbol, position.average_price)
            market_value = Decimal(position.quantity) * price
            pnl = (price - position.average_price) * Decimal(position.quantity)
            unrealized += pnl
            gross += abs(market_value)
            net += market_value
            sector = sector_map.get(symbol, "Unknown")
            sector_exposure[sector] = sector_exposure.get(sector, Decimal("0")) + market_value
            if position.quantity != 0:
                positions.append(
                    Position(
                        symbol=symbol,
                        quantity=position.quantity,
                        average_price=float(position.average_price),
                        market_price=float(price),
                        market_value=float(market_value),
                        unrealized_pnl=float(pnl),
                    )
                )
        equity = self.cash + net
        return PortfolioState(
            cash=float(self.cash),
            equity=float(equity),
            realized_pnl=float(self.realized_pnl),
            unrealized_pnl=float(unrealized),
            gross_exposure=float(gross),
            net_exposure=float(net),
            sector_exposure={sector: float(value) for sector, value in sector_exposure.items()},
            positions=positions,
        )
