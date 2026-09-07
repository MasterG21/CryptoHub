"""Position sizing and the circuit breakers that keep a losing run survivable.

Sizing is fixed-fractional against the stop: risk a constant share of equity
per trade, and let the distance to the stop decide how many tokens that buys.
The account then shrinks its bet size automatically while losing and grows it
while winning, which is what makes compounding from a small base possible at
all without a single bad week ending it.

Four independent caps apply, and the smallest wins:

  1. **Risk cap** — equity x risk_per_trade / stop distance.
  2. **Position cap** — no one token gets an outsized share of the account.
  3. **Pool-impact cap** — the one that usually binds. On a thin pool you are
     the price: taking 5% of the depth costs roughly 5% on entry and again on
     exit, which is a fifth of a 30% stop paid straight to slippage.
  4. **Cash cap** — what is actually free to deploy, reserve held back.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from .config import RiskConfig
from .models import Chain, Pair


@dataclass
class SizingResult:
    usd_amount: float
    binding_constraint: str
    rejected_reason: Optional[str] = None
    caps: dict[str, float] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.rejected_reason is None and self.usd_amount > 0


def size_position(
    equity_usd: float,
    cash_usd: float,
    entry_price: float,
    stop_price: float,
    pair: Pair,
    cfg: RiskConfig,
) -> SizingResult:
    """Work out how many dollars to put into one entry."""
    if entry_price <= 0:
        return SizingResult(0.0, "none", "entry price is not positive")
    if stop_price <= 0 or stop_price >= entry_price:
        return SizingResult(0.0, "none", "stop must sit below the entry price")
    if pair.liquidity_usd is None:
        return SizingResult(0.0, "none", "pool liquidity unknown; cannot size safely")

    stop_distance_pct = (entry_price - stop_price) / entry_price
    risk_budget = equity_usd * cfg.risk_per_trade_pct
    caps = {
        "risk": risk_budget / stop_distance_pct,
        "position": equity_usd * cfg.max_position_pct,
        "pool_impact": pair.liquidity_usd * cfg.max_pool_impact_pct,
        "cash": max(0.0, cash_usd - equity_usd * cfg.cash_reserve_pct),
    }
    binding = min(caps, key=lambda k: caps[k])
    amount = caps[binding]

    if amount < cfg.min_position_usd:
        return SizingResult(
            0.0,
            binding,
            (
                f"sized at ${amount:.2f}, under the ${cfg.min_position_usd:.2f} minimum "
                f"({binding} cap binding)"
            ),
            caps=caps,
        )
    return SizingResult(round(amount, 2), binding, caps=caps)


@dataclass
class RiskState:
    """Rolling risk counters. Persisted so a restart cannot reset a bad day."""

    day: str = ""
    day_start_equity: float = 0.0
    realized_today_usd: float = 0.0
    consecutive_losses: int = 0
    trades_today: int = 0
    halted_reason: Optional[str] = None

    @staticmethod
    def _today(now: Optional[float] = None) -> str:
        return time.strftime("%Y-%m-%d", time.gmtime(now if now is not None else time.time()))

    def roll_day(self, equity_usd: float, now: Optional[float] = None) -> bool:
        """Start a new UTC day if needed. Returns True if the day rolled.

        Rolling clears the daily loss halt but deliberately leaves
        ``consecutive_losses`` alone: a losing streak does not become less real
        because midnight passed.
        """
        today = self._today(now)
        if self.day == today:
            return False
        self.day = today
        self.day_start_equity = equity_usd
        self.realized_today_usd = 0.0
        self.trades_today = 0
        if self.halted_reason and "daily loss" in self.halted_reason:
            self.halted_reason = None
        return True

    def record_close(self, pnl_usd: float) -> None:
        self.realized_today_usd += pnl_usd
        self.trades_today += 1
        if pnl_usd < 0:
            self.consecutive_losses += 1
        elif pnl_usd > 0:
            self.consecutive_losses = 0


class RiskManager:
    """Owns the kill switches. The desk asks it before every entry."""

    def __init__(self, cfg: RiskConfig, state: Optional[RiskState] = None):
        self.cfg = cfg
        self.state = state or RiskState()

    def sync_day(self, equity_usd: float, now: Optional[float] = None) -> bool:
        if not self.state.day:
            self.state.day = RiskState._today(now)
            self.state.day_start_equity = equity_usd
            return False
        return self.state.roll_day(equity_usd, now)

    def check_halt(self, equity_usd: float) -> Optional[str]:
        """Return a halt reason, or None if the desk may open new positions.

        A halt stops *entries* only. Open positions keep being managed and
        exited normally — freezing a book of memecoins in place because the
        day went badly is how a bad day becomes a total loss.
        """
        cfg, state = self.cfg, self.state
        if equity_usd <= cfg.equity_floor_usd:
            state.halted_reason = (
                f"equity ${equity_usd:.2f} at or below the ${cfg.equity_floor_usd:.2f} floor"
            )
            return state.halted_reason
        if state.day_start_equity > 0:
            drawdown = 1 - equity_usd / state.day_start_equity
            if drawdown >= cfg.daily_loss_limit_pct:
                state.halted_reason = (
                    f"down {drawdown * 100:.1f}% today, past the "
                    f"{cfg.daily_loss_limit_pct * 100:.0f}% daily loss limit"
                )
                return state.halted_reason
        if state.consecutive_losses >= cfg.max_consecutive_losses:
            state.halted_reason = (
                f"{state.consecutive_losses} losing trades in a row; "
                "the setup is not working today"
            )
            return state.halted_reason
        state.halted_reason = None
        return None

    def capacity(self, open_positions: list) -> int:
        return max(0, self.cfg.max_concurrent_positions - len(open_positions))

    def chain_has_room(self, chain: Chain, open_positions: list) -> bool:
        held = sum(1 for p in open_positions if p.chain is chain)
        return held < self.cfg.max_positions_per_chain

    def clear_halt(self) -> None:
        """Manual override, used by the CLI's ``resume`` command."""
        self.state.halted_reason = None
        self.state.consecutive_losses = 0
