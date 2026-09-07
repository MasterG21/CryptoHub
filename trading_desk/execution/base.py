"""Execution interface and the AMM cost model both engines share.

Price impact here is derived from the constant-product invariant rather than
assumed as a flat percentage, because on a memecoin pool the order *is* the
market move. For a pool holding ``Q`` dollars on the quote side (about half of
reported liquidity):

    buying with ``d`` dollars   -> effective price = spot * (1 + d/Q)
    selling ``d`` dollars worth -> effective price = spot * (1 - (d/Q)/(1 + d/Q))

Buys and sells are asymmetric, and the sell side is the one that bites: the
same notional that costs 5% going in costs about 4.8% coming out, on top of
whatever the price did in between. Ignoring this is the single most common
reason a paper-trading memecoin strategy looks profitable and is not.

Concentrated-liquidity pools (Uniswap V3, and most of what trades on BNB
Chain) are *deeper than this model near spot and much shallower outside the
active range*, so treat these numbers as a well-founded approximation, not a
quote. Real routing numbers come from the aggregator in ``live.py``.
"""
from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from ..models import Fill, Order, Pair


class ExecutionError(RuntimeError):
    """An order could not be executed."""


class SlippageExceeded(ExecutionError):
    """The order would move the price further than the caller allowed."""

    def __init__(self, required_pct: float, allowed_pct: float):
        self.required_pct = required_pct
        self.allowed_pct = allowed_pct
        super().__init__(
            f"order needs {required_pct * 100:.1f}% slippage tolerance, "
            f"limit is {allowed_pct * 100:.1f}%"
        )


def quote_side_depth(liquidity_usd: float) -> float:
    """The dollar side of the pool: reported liquidity counts both sides."""
    return max(1e-9, liquidity_usd / 2.0)


def buy_impact_pct(usd_amount: float, liquidity_usd: Optional[float]) -> float:
    """Fractional price impact of buying ``usd_amount`` from this pool."""
    if not liquidity_usd or liquidity_usd <= 0:
        return 1.0  # unknown depth is treated as unlimited impact, never as none
    return usd_amount / quote_side_depth(liquidity_usd)


def sell_impact_pct(usd_notional: float, liquidity_usd: Optional[float]) -> float:
    """Fractional price impact of selling ``usd_notional`` worth into this pool."""
    if not liquidity_usd or liquidity_usd <= 0:
        return 1.0
    ratio = usd_notional / quote_side_depth(liquidity_usd)
    return ratio / (1.0 + ratio)


def round_trip_cost_pct(usd_amount: float, liquidity_usd: Optional[float], fee_pct: float) -> float:
    """What a full in-and-out costs before the price moves at all.

    Useful as a sanity check on position size: if a round trip costs 12%, a
    30% stop is really a 42% stop and the strategy's arithmetic no longer
    works.
    """
    return (
        buy_impact_pct(usd_amount, liquidity_usd)
        + sell_impact_pct(usd_amount, liquidity_usd)
        + 2 * fee_pct
    )


@runtime_checkable
class Executor(Protocol):
    """Turns an ``Order`` into a ``Fill``, or raises ``ExecutionError``."""

    name: str

    def execute(self, order: Order, pair: Optional[Pair] = None) -> Fill:
        ...
