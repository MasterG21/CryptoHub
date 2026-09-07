"""Cash, positions and mark-to-market equity.

The portfolio is the single source of truth for what the desk owns. It applies
fills, keeps cost basis correct across partial exits, and reports equity that
already accounts for the fact that a memecoin position is worth what you could
sell it for, not what the last trade printed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .models import Chain, Fill, Pair, Position


@dataclass
class ClosedTrade:
    """A fully or partially closed line, recorded for the journal and stats."""

    chain: Chain
    token_address: str
    symbol: str
    quantity: float
    entry_price: float
    exit_price: float
    proceeds_usd: float
    cost_usd: float
    reason: str
    opened_at: float
    closed_at: float

    @property
    def pnl_usd(self) -> float:
        return self.proceeds_usd - self.cost_usd

    @property
    def return_pct(self) -> float:
        if self.cost_usd <= 0:
            return 0.0
        return self.pnl_usd / self.cost_usd

    @property
    def holding_minutes(self) -> float:
        return (self.closed_at - self.opened_at) / 60.0


class Portfolio:
    def __init__(self, starting_cash_usd: float):
        self.starting_cash_usd = starting_cash_usd
        self.cash_usd = starting_cash_usd
        self.positions: dict[str, Position] = {}
        self.closed_trades: list[ClosedTrade] = []
        self.fees_paid_usd = 0.0

    # ------------------------------------------------------------------ state

    @property
    def open_positions(self) -> list[Position]:
        return list(self.positions.values())

    def get(self, chain: Chain, token_address: str) -> Optional[Position]:
        return self.positions.get(f"{chain.value}:{token_address.lower()}")

    def holds(self, chain: Chain, token_address: str) -> bool:
        return self.get(chain, token_address) is not None

    @property
    def positions_value_usd(self) -> float:
        return sum(p.market_value_usd for p in self.positions.values())

    @property
    def equity_usd(self) -> float:
        return self.cash_usd + self.positions_value_usd

    @property
    def realized_pnl_usd(self) -> float:
        return sum(t.pnl_usd for t in self.closed_trades)

    @property
    def unrealized_pnl_usd(self) -> float:
        return sum(p.unrealized_usd for p in self.positions.values())

    @property
    def total_return_pct(self) -> float:
        if self.starting_cash_usd <= 0:
            return 0.0
        return self.equity_usd / self.starting_cash_usd - 1.0

    # ------------------------------------------------------------------- fills

    def apply_buy(self, fill: Fill, pair: Optional[Pair], stop_price: float) -> Position:
        """Open or add to a position. Cost basis includes fees and gas."""
        cash_out = -fill.net_usd  # net_usd is negative for buys
        self.cash_usd -= cash_out
        self.fees_paid_usd += fill.fee_usd + fill.gas_usd

        key = f"{fill.order.chain.value}:{fill.order.token_address.lower()}"
        existing = self.positions.get(key)
        if existing is None:
            position = Position(
                chain=fill.order.chain,
                token_address=fill.order.token_address,
                symbol=fill.order.symbol,
                quantity=fill.quantity,
                avg_entry_price=fill.price,
                cost_basis_usd=cash_out,
                stop_price=stop_price,
                opened_at=fill.timestamp,
                high_water_price=fill.price,
                last_price=fill.price,
                entry_liquidity_usd=pair.liquidity_usd if pair else None,
                last_liquidity_usd=pair.liquidity_usd if pair else None,
                pair_address=pair.pair_address if pair else None,
                initial_quantity=fill.quantity,
            )
            self.positions[key] = position
            return position

        total_qty = existing.quantity + fill.quantity
        existing.avg_entry_price = (
            existing.avg_entry_price * existing.quantity + fill.price * fill.quantity
        ) / total_qty
        existing.quantity = total_qty
        existing.initial_quantity += fill.quantity
        existing.cost_basis_usd += cash_out
        existing.last_price = fill.price
        existing.stop_price = stop_price
        if fill.price > existing.high_water_price:
            existing.high_water_price = fill.price
        return existing

    def apply_sell(self, fill: Fill, reason: str = "") -> Optional[ClosedTrade]:
        """Reduce or close a position, booking the realised P&L.

        Cost basis is released in proportion to the quantity sold, so a partial
        exit leaves the remainder carrying its own share of the original cost
        and the reported unrealised P&L stays honest.
        """
        key = f"{fill.order.chain.value}:{fill.order.token_address.lower()}"
        position = self.positions.get(key)
        if position is None:
            return None

        quantity = min(fill.quantity, position.quantity)
        proceeds = fill.net_usd  # positive for sells, net of fees and gas
        self.cash_usd += proceeds
        self.fees_paid_usd += fill.fee_usd + fill.gas_usd

        share = quantity / position.quantity if position.quantity else 1.0
        released_cost = position.cost_basis_usd * share
        position.cost_basis_usd -= released_cost
        position.quantity -= quantity
        position.realized_usd += proceeds - released_cost
        position.last_price = fill.price

        trade = ClosedTrade(
            chain=position.chain,
            token_address=position.token_address,
            symbol=position.symbol,
            quantity=quantity,
            entry_price=position.avg_entry_price,
            exit_price=fill.price,
            proceeds_usd=proceeds,
            cost_usd=released_cost,
            reason=reason,
            opened_at=position.opened_at,
            closed_at=fill.timestamp,
        )
        self.closed_trades.append(trade)

        if position.quantity <= 1e-12:
            self.positions.pop(key, None)
        return trade

    # --------------------------------------------------------------- reporting

    def mark(self, quotes: dict[str, Pair]) -> None:
        """Refresh every position's last price from the latest quotes."""
        for key, position in self.positions.items():
            pair = quotes.get(key)
            if pair and pair.price_usd:
                position.last_price = pair.price_usd
                if pair.liquidity_usd is not None:
                    position.last_liquidity_usd = pair.liquidity_usd
                if pair.price_usd > position.high_water_price:
                    position.high_water_price = pair.price_usd

    def stats(self) -> dict:
        """Aggregate performance, the numbers that say whether the edge is real."""
        trades = self.closed_trades
        wins = [t for t in trades if t.pnl_usd > 0]
        losses = [t for t in trades if t.pnl_usd <= 0]
        gross_win = sum(t.pnl_usd for t in wins)
        gross_loss = -sum(t.pnl_usd for t in losses)
        return {
            "trades": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": len(wins) / len(trades) if trades else 0.0,
            "avg_win_usd": gross_win / len(wins) if wins else 0.0,
            "avg_loss_usd": -gross_loss / len(losses) if losses else 0.0,
            "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else None,
            "best_usd": max((t.pnl_usd for t in trades), default=0.0),
            "worst_usd": min((t.pnl_usd for t in trades), default=0.0),
            "fees_paid_usd": self.fees_paid_usd,
            "equity_usd": self.equity_usd,
            "cash_usd": self.cash_usd,
            "open_positions": len(self.positions),
            "total_return_pct": self.total_return_pct,
        }
