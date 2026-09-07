"""The autonomous loop: discover, screen, size, enter, manage, exit.

One ``tick()`` is the whole desk. It runs in a fixed order, and the order is
the design:

  1. **Refresh** quotes for open positions.
  2. **Exit** anything that has hit a rule. Exits run before entries, always,
     including while halted — freeing capital and cutting losers can never be
     blocked by an entry-side circuit breaker.
  3. **Check the kill switch.** If it has tripped, the tick ends here.
  4. **Discover** candidates, run the safety gate, then score momentum.
  5. **Size and enter** the best of what survived, up to capacity.
  6. **Snapshot** equity and persist everything.

Every step is wrapped so a failure in one chain, one feed or one token cannot
stop the others; failures accumulate into ``TickResult.errors`` for the caller
to surface rather than being swallowed.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from .config import DeskConfig
from .execution.base import Executor, ExecutionError, SlippageExceeded
from .journal import Journal
from .marketdata.base import MultiChainFeed
from .marketdata.history import PriceHistory
from .models import Candidate, ExitReason, Fill, Order, Pair, Position, Side
from .portfolio import Portfolio
from .risk import RiskManager, size_position
from .safety import SafetyGate
from .strategy import (
    apply_post_exit_adjustments,
    evaluate_entry,
    evaluate_exit,
    initial_stop_price,
)

log = logging.getLogger("trading_desk")

# How far past the configured tolerance the desk will reach to get *out* of a
# position. Being unable to exit is the failure mode that turns a bad trade
# into a total loss, so an exit is allowed to pay more than an entry would.
FORCED_EXIT_SLIPPAGE_PCT = 0.45


@dataclass
class TickResult:
    started_at: float
    equity_usd: float = 0.0
    cash_usd: float = 0.0
    scanned: int = 0
    safety_rejected: int = 0
    scored: int = 0
    entries: list[str] = field(default_factory=list)
    exits: list[str] = field(default_factory=list)
    halted_reason: Optional[str] = None
    errors: list[str] = field(default_factory=list)
    top_candidates: list[Candidate] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float:
        return time.time() - self.started_at


class TradingDesk:
    """Owns the portfolio, the risk manager and the loop that drives them."""

    def __init__(
        self,
        config: DeskConfig,
        feed: MultiChainFeed,
        executor: Executor,
        journal: Optional[Journal] = None,
        safety_gate: Optional[SafetyGate] = None,
        history: Optional[PriceHistory] = None,
        clock: Callable[[], float] = time.time,
    ):
        self.config = config
        self.feed = feed
        self.executor = executor
        self.journal = journal
        self.history = history or PriceHistory()
        self.safety = safety_gate or SafetyGate(config.safety, history=self.history)
        self.clock = clock

        if journal is not None:
            self.portfolio = journal.load_portfolio(config.starting_capital_usd)
            self.risk = RiskManager(config.risk, journal.load_risk_state())
        else:
            self.portfolio = Portfolio(config.starting_capital_usd)
            self.risk = RiskManager(config.risk)
        self.risk.sync_day(self.portfolio.equity_usd)
        self.recent_exits: dict[str, float] = (
            journal.load_recent_exits() if journal is not None else {}
        )
        self.ticks = 0

    # ------------------------------------------------------------------- loop

    def tick(self) -> TickResult:
        result = TickResult(started_at=self.clock())
        self.ticks += 1

        # A halted desk never reaches discover(), which is what normally clears
        # these; without this they would grow for as long as the halt lasts.
        self.feed.reset_errors()
        quotes = self._refresh_positions(result)
        self._process_exits(quotes, result)

        equity = self.portfolio.equity_usd
        self.risk.sync_day(equity)
        result.halted_reason = self.risk.check_halt(equity)

        if result.halted_reason is None:
            self._process_entries(result)

        result.equity_usd = self.portfolio.equity_usd
        result.cash_usd = self.portfolio.cash_usd
        self._persist(result)
        return result

    def run(
        self,
        max_ticks: Optional[int] = None,
        on_tick: Optional[Callable[[TickResult], None]] = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> list[TickResult]:
        """Run the loop until interrupted, or for ``max_ticks`` iterations.

        A crash in one tick is logged and the loop continues: an unhandled
        exception at 3am must not leave open positions with nothing managing
        their stops.
        """
        results: list[TickResult] = []
        try:
            while max_ticks is None or len(results) < max_ticks:
                try:
                    result = self.tick()
                except Exception as exc:  # noqa: BLE001
                    log.exception("tick failed")
                    result = TickResult(started_at=self.clock(), errors=[f"tick failed: {exc}"])
                results.append(result)
                if on_tick:
                    on_tick(result)
                if max_ticks is None or len(results) < max_ticks:
                    sleep(self.config.poll_interval_seconds)
        except KeyboardInterrupt:
            log.info("interrupted; open positions left in place")
        return results

    # ----------------------------------------------------------------- stages

    def _refresh_positions(self, result: TickResult) -> dict[str, Pair]:
        """Re-quote every open position. A stale mark is a broken stop."""
        quotes: dict[str, Pair] = {}
        for position in self.portfolio.open_positions:
            pair = self.feed.get_pair(position.chain, position.token_address)
            if pair is None or not pair.price_usd:
                result.errors.append(
                    f"no fresh quote for {position.symbol} on {position.chain.label}; "
                    "holding last mark"
                )
                continue
            quotes[position.key] = pair
            self.history.observe(pair.key, pair.price_usd, pair.liquidity_usd)
        self.portfolio.mark(quotes)
        return quotes

    def _process_exits(self, quotes: dict[str, Pair], result: TickResult) -> None:
        for position in list(self.portfolio.open_positions):
            pair = quotes.get(position.key)
            try:
                decision = evaluate_exit(position, pair, self.config.strategy)
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"exit check failed for {position.symbol}: {exc}")
                continue
            if decision is None:
                continue

            quantity = position.quantity * decision.fraction
            fill = self._sell(position, pair, quantity, decision.reason, decision.note, result)
            if fill is None:
                continue

            trade = self.portfolio.apply_sell(fill, reason=decision.reason.value)
            apply_post_exit_adjustments(position, decision, self.config.strategy)
            if trade is None:
                continue
            if self.journal:
                self.journal.record_trade(trade)

            # Only a fully closed line counts toward the losing-streak breaker,
            # and it counts once, for the whole line: banking a profitable
            # tranche of a trade that later stops out is not a separate win.
            # position.realized_usd has accumulated every tranche by now.
            fully_closed = position.quantity <= 1e-12
            if fully_closed:
                self.risk.state.record_close(position.realized_usd)
                self.recent_exits[position.key] = self.clock()
            booked = position.realized_usd if fully_closed else trade.pnl_usd
            result.exits.append(
                f"{position.symbol} {decision.reason.value} "
                f"{booked:+.2f} USD ({decision.note})"
            )

    def _process_entries(self, result: TickResult) -> None:
        capacity = self.risk.capacity(self.portfolio.open_positions)
        if capacity <= 0:
            return

        pairs = self.feed.discover(limit_per_chain=self.config.max_candidates_per_chain)
        result.errors += [f"{chain.label}: {msg}" for chain, msg in self.feed.errors]
        result.scanned = len(pairs)

        cooling_off = self._cooling_off()
        candidates: list[Candidate] = []
        for pair in pairs:
            if pair.price_usd:
                self.history.observe(pair.key, pair.price_usd, pair.liquidity_usd)
            if self.portfolio.holds(pair.chain, pair.base_address):
                continue
            if pair.key in cooling_off:
                continue
            try:
                verdict = self.safety.evaluate(pair)
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"safety check failed for {pair.base_symbol}: {exc}")
                continue
            if not verdict.passed:
                result.safety_rejected += 1
                continue
            candidates.append(evaluate_entry(pair, verdict, self.config.strategy))

        result.scored = len(candidates)
        tradeable = sorted(
            (c for c in candidates if c.tradeable), key=lambda c: c.score, reverse=True
        )
        result.top_candidates = sorted(candidates, key=lambda c: c.score, reverse=True)[:5]

        for candidate in tradeable:
            if capacity <= 0:
                break
            if not self.risk.chain_has_room(candidate.pair.chain, self.portfolio.open_positions):
                continue
            if self._enter(candidate, result):
                capacity -= 1

    def _cooling_off(self) -> set[str]:
        """Tokens closed too recently to buy back, pruned as they age out."""
        cutoff = self.clock() - self.config.strategy.reentry_cooldown_minutes * 60
        self.recent_exits = {k: ts for k, ts in self.recent_exits.items() if ts >= cutoff}
        return set(self.recent_exits)

    # ------------------------------------------------------------------ trades

    def _enter(self, candidate: Candidate, result: TickResult) -> bool:
        pair = candidate.pair
        price = pair.price_usd
        if not price:
            return False

        stop = initial_stop_price(price, self.config.strategy)
        sizing = size_position(
            equity_usd=self.portfolio.equity_usd,
            cash_usd=self.portfolio.cash_usd,
            entry_price=price,
            stop_price=stop,
            pair=pair,
            cfg=self.config.risk,
        )
        if not sizing.ok:
            return False

        order = Order(
            chain=pair.chain,
            token_address=pair.base_address,
            symbol=pair.base_symbol,
            side=Side.BUY,
            usd_amount=sizing.usd_amount,
            reference_price=price,
            pair=pair,
            reason=f"score {candidate.score:.2f} ({sizing.binding_constraint}-capped)",
            max_slippage_pct=self.config.execution.max_slippage_pct,
        )
        try:
            fill = self.executor.execute(order, pair)
        except SlippageExceeded as exc:
            result.errors.append(f"skipped {pair.base_symbol}: {exc}")
            return False
        except ExecutionError as exc:
            result.errors.append(f"entry failed for {pair.base_symbol}: {exc}")
            return False

        self.portfolio.apply_buy(fill, pair, stop_price=stop)
        if self.journal:
            self.journal.record_fill(fill)
        result.entries.append(
            f"{pair.base_symbol} on {pair.chain.label} ${sizing.usd_amount:.2f} "
            f"@ ${fill.price:.8g} (score {candidate.score:.2f})"
        )
        return True

    def _sell(
        self,
        position: Position,
        pair: Optional[Pair],
        quantity: float,
        reason: ExitReason,
        note: str,
        result: TickResult,
    ) -> Optional[Fill]:
        """Sell, escalating the slippage tolerance once if the exit is urgent.

        A stop that will not fill is not a stop. When an exit is forced —
        anything but a scale-out — the desk retries at a wider tolerance and
        records that it paid up, rather than quietly leaving the position on.
        """
        order = Order(
            chain=position.chain,
            token_address=position.token_address,
            symbol=position.symbol,
            side=Side.SELL,
            quantity=quantity,
            reference_price=position.last_price,
            pair=pair,
            reason=f"{reason.value}: {note}",
            max_slippage_pct=self.config.execution.max_slippage_pct,
        )
        try:
            return self.executor.execute(order, pair)
        except SlippageExceeded as exc:
            if reason is ExitReason.TAKE_PROFIT:
                result.errors.append(f"scale-out of {position.symbol} skipped: {exc}")
                return None
            order.max_slippage_pct = max(FORCED_EXIT_SLIPPAGE_PCT, exc.required_pct)
            result.errors.append(
                f"forcing {reason.value} exit of {position.symbol} at "
                f"{exc.required_pct * 100:.0f}% slippage"
            )
            try:
                return self.executor.execute(order, pair)
            except ExecutionError as inner:
                result.errors.append(f"could not exit {position.symbol}: {inner}")
                return None
        except ExecutionError as exc:
            result.errors.append(f"exit failed for {position.symbol}: {exc}")
            return None

    # -------------------------------------------------------------- lifecycle

    def close_all(self, reason: ExitReason = ExitReason.MANUAL) -> list[str]:
        """Flatten the book. Used by the CLI's ``panic`` command."""
        closed: list[str] = []
        result = TickResult(started_at=self.clock())
        for position in list(self.portfolio.open_positions):
            pair = self.feed.get_pair(position.chain, position.token_address)
            if pair and pair.price_usd:
                position.last_price = pair.price_usd
            fill = self._sell(position, pair, position.quantity, reason, "flatten", result)
            if fill is None:
                continue
            trade = self.portfolio.apply_sell(fill, reason=reason.value)
            if trade and self.journal:
                self.journal.record_trade(trade)
            if trade:
                self.recent_exits[position.key] = self.clock()
                closed.append(f"{position.symbol} {trade.pnl_usd:+.2f} USD")
        self._persist(result)
        return closed

    def _persist(self, result: TickResult) -> None:
        if self.journal is None:
            return
        try:
            self.journal.snapshot_equity(self.portfolio)
            self.journal.save_state(self.portfolio, self.risk.state, self.recent_exits)
        except Exception as exc:  # noqa: BLE001 - never let disk kill the loop
            result.errors.append(f"journal write failed: {exc}")

    def progress_to_target(self) -> dict:
        """Where the account stands against the target it was pointed at."""
        equity = self.portfolio.equity_usd
        start = self.portfolio.starting_cash_usd
        target = self.config.target_usd
        remaining = target / equity if equity > 0 else float("inf")
        return {
            "equity_usd": equity,
            "starting_usd": start,
            "target_usd": target,
            "multiple_achieved": equity / start if start else 0.0,
            "multiple_remaining": remaining,
            "pct_of_target": equity / target if target else 0.0,
        }
