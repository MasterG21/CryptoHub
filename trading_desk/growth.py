"""What getting from $100 to $1,000,000 actually requires.

A 10,000x is not a stretch goal, it is a different kind of problem from a
trading strategy, and this module exists so the desk can say so in numbers
rather than in adjectives.

The core arithmetic: under fixed-fractional sizing, equity compounds by
``1 + f*R`` per trade, where ``f`` is the fraction of equity risked and ``R``
is the trade's outcome in units of the risk taken. Growth per trade is
therefore ``E[ln(1 + f*R)]`` — the *log* mean, not the arithmetic one, and the
gap between the two is where accounts die. A strategy with positive expectancy
can still have negative log growth if it is bet too large, and it will then go
to zero with probability approaching one no matter how good the edge is.

The default distribution below is an assumption, not a measurement. It is
shaped like a memecoin momentum book — mostly stop-outs, occasional multi-R
winners — but the honest way to use this module is to replace it with your own
realised distribution from ``Portfolio.stats()`` once the desk has traded
enough to have one, via ``TradeDistribution.from_trades``.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence


@dataclass(frozen=True)
class Outcome:
    probability: float
    r_multiple: float  # profit/loss as a multiple of the risk taken
    label: str = ""


@dataclass
class TradeDistribution:
    """The per-trade outcome distribution, in R-multiples."""

    outcomes: tuple[Outcome, ...]

    def __post_init__(self) -> None:
        total = sum(o.probability for o in self.outcomes)
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"outcome probabilities sum to {total:.4f}, not 1.0")

    @property
    def expectancy_r(self) -> float:
        """Arithmetic expectancy. Positive is necessary, not sufficient."""
        return sum(o.probability * o.r_multiple for o in self.outcomes)

    @property
    def win_rate(self) -> float:
        return sum(o.probability for o in self.outcomes if o.r_multiple > 0)

    @property
    def worst_r(self) -> float:
        return min(o.r_multiple for o in self.outcomes)

    def sample(self, rng: random.Random) -> float:
        draw = rng.random()
        cumulative = 0.0
        for outcome in self.outcomes:
            cumulative += outcome.probability
            if draw <= cumulative:
                return outcome.r_multiple
        return self.outcomes[-1].r_multiple

    def log_growth_per_trade(self, fraction: float) -> float:
        """``E[ln(1 + f*R)]`` — the rate equity actually compounds at.

        Returns -inf for any fraction that can produce a total loss, because a
        bet that can zero the account has no long-run growth rate at all.
        """
        total = 0.0
        for outcome in self.outcomes:
            factor = 1 + fraction * outcome.r_multiple
            if factor <= 0:
                return float("-inf")
            total += outcome.probability * math.log(factor)
        return total

    def optimal_fraction(self, cap: float = 0.95, steps: int = 2000) -> float:
        """The growth-optimal risk fraction (full Kelly) for this distribution.

        Found by scanning rather than solving, because the outcome set is
        discrete and small. Betting *more* than this reduces growth and raises
        ruin simultaneously — it is not a risk/reward trade, it is strictly
        worse on both. Most practitioners run a fraction of it (half or
        quarter Kelly) because the input distribution is never known exactly.
        """
        best_f, best_g = 0.0, 0.0
        for i in range(1, steps + 1):
            f = cap * i / steps
            g = self.log_growth_per_trade(f)
            if g > best_g:
                best_f, best_g = f, g
        return best_f

    @classmethod
    def from_trades(cls, r_multiples: Sequence[float], buckets: int = 8) -> "TradeDistribution":
        """Build an empirical distribution from realised R-multiples."""
        values = [r for r in r_multiples if r is not None]
        if not values:
            raise ValueError("no trades to build a distribution from")
        ordered = sorted(values)
        size = max(1, len(ordered) // buckets)
        chunks = [ordered[i : i + size] for i in range(0, len(ordered), size)]
        outcomes = tuple(
            Outcome(
                probability=len(chunk) / len(ordered),
                r_multiple=sum(chunk) / len(chunk),
                label=f"bucket {i + 1}",
            )
            for i, chunk in enumerate(chunks)
        )
        # Floating-point bucket weights rarely sum to exactly 1.
        drift = 1.0 - sum(o.probability for o in outcomes)
        if abs(drift) > 1e-12:
            last = outcomes[-1]
            outcomes = outcomes[:-1] + (
                Outcome(last.probability + drift, last.r_multiple, last.label),
            )
        return cls(outcomes=outcomes)


# A memecoin momentum book, shaped by this desk's own exit rules: a 30% stop,
# scale-outs at 2x/4x/10x, and a time stop that cuts the ones that go nowhere.
# The tail is what pays for everything else — remove the 2% column and the
# whole distribution goes negative.
DEFAULT_DISTRIBUTION = TradeDistribution(
    outcomes=(
        Outcome(0.62, -1.10, "stopped out (slippage past the stop)"),
        Outcome(0.20, -0.35, "time stop / momentum died"),
        Outcome(0.10, 1.20, "small winner, trailed out"),
        Outcome(0.06, 5.00, "reached the 2-4x ladder"),
        Outcome(0.02, 18.00, "the one that ran"),
    )
)


@dataclass
class GrowthMath:
    """Closed-form answers about the path from start to target."""

    start_usd: float
    target_usd: float
    fraction: float
    distribution: TradeDistribution

    @property
    def required_multiple(self) -> float:
        return self.target_usd / self.start_usd

    @property
    def log_growth(self) -> float:
        return self.distribution.log_growth_per_trade(self.fraction)

    @property
    def trades_required(self) -> Optional[float]:
        """Expected number of trades to reach the target, if it is reachable.

        None when log growth is zero or negative — meaning the target is not
        merely far away, it is not on the path at all: the account trends to
        zero and no amount of patience changes that.
        """
        growth = self.log_growth
        if growth <= 0 or growth == float("-inf"):
            return None
        return math.log(self.required_multiple) / growth

    def days_required(self, trades_per_day: float) -> Optional[float]:
        trades = self.trades_required
        if trades is None or trades_per_day <= 0:
            return None
        return trades / trades_per_day

    @property
    def optimal_fraction(self) -> float:
        return self.distribution.optimal_fraction()

    @property
    def overbet(self) -> bool:
        """True when the configured risk sits past the growth-optimal peak."""
        return self.fraction > self.optimal_fraction


@dataclass
class SimulationResult:
    runs: int
    trades_per_run: int
    reached_target: int
    ruined: int
    stalled: int = 0
    terminal_equity: list[float] = field(default_factory=list)
    trades_to_target: list[int] = field(default_factory=list)
    peak_equity: list[float] = field(default_factory=list)

    @property
    def p_target(self) -> float:
        return self.reached_target / self.runs if self.runs else 0.0

    @property
    def p_ruin(self) -> float:
        """Fell through the equity floor the desk halts at."""
        return self.ruined / self.runs if self.runs else 0.0

    @property
    def p_stalled(self) -> float:
        """Still has money, but not enough to place the smallest valid trade.

        Tracked separately from ruin because it looks different in a balance
        and is the same thing in practice: the account cannot make another
        trade, so it cannot recover.
        """
        return self.stalled / self.runs if self.runs else 0.0

    @property
    def p_dead(self) -> float:
        """Ruined or stalled — every way the account stops being a going concern."""
        return self.p_ruin + self.p_stalled

    def percentile(self, pct: float) -> float:
        if not self.terminal_equity:
            return 0.0
        ordered = sorted(self.terminal_equity)
        idx = min(len(ordered) - 1, max(0, int(pct / 100 * len(ordered))))
        return ordered[idx]

    @property
    def median_equity(self) -> float:
        return self.percentile(50)

    @property
    def mean_equity(self) -> float:
        return sum(self.terminal_equity) / len(self.terminal_equity) if self.terminal_equity else 0.0

    @property
    def median_trades_to_target(self) -> Optional[float]:
        if not self.trades_to_target:
            return None
        ordered = sorted(self.trades_to_target)
        return ordered[len(ordered) // 2]


def simulate(
    start_usd: float = 100.0,
    target_usd: float = 1_000_000.0,
    fraction: float = 0.06,
    trades: int = 2000,
    runs: int = 5000,
    distribution: Optional[TradeDistribution] = None,
    ruin_floor_usd: float = 15.0,
    min_position_usd: float = 5.0,
    stop_loss_pct: float = 0.30,
    seed: Optional[int] = 7,
) -> SimulationResult:
    """Monte-Carlo the account forward under fixed-fractional sizing.

    Two frictions from the real desk are modelled because they dominate the
    small-account case and flatter simulations leave them out:

      * **Ruin floor** — below ``ruin_floor_usd`` the desk halts, so a run that
        gets there is over. It does not get to make a heroic recovery from $3.
      * **Minimum position** — risking ``f`` of equity across a
        ``stop_loss_pct`` stop implies a position of
        ``equity * f / stop_loss_pct``. Once that falls under
        ``min_position_usd`` there is no trade left to place: gas and DEX
        minimums do not scale down with your account.
    """
    rng = random.Random(seed)
    dist = distribution or DEFAULT_DISTRIBUTION
    result = SimulationResult(runs=runs, trades_per_run=trades, reached_target=0, ruined=0)

    for _ in range(runs):
        equity = start_usd
        peak = equity
        hit_at: Optional[int] = None
        stalled = False
        for trade_no in range(1, trades + 1):
            if equity <= ruin_floor_usd:
                break
            # The position the risk budget implies has to clear the floor that
            # gas and DEX minimums impose.
            if equity * fraction / stop_loss_pct < min_position_usd:
                stalled = True
                break
            equity *= 1 + fraction * dist.sample(rng)
            peak = max(peak, equity)
            if equity >= target_usd:
                hit_at = trade_no
                break

        result.terminal_equity.append(equity)
        result.peak_equity.append(peak)
        if hit_at is not None:
            result.reached_target += 1
            result.trades_to_target.append(hit_at)
        elif equity <= ruin_floor_usd:
            result.ruined += 1
        elif stalled:
            result.stalled += 1

    return result


def milestone_ladder(
    start_usd: float, target_usd: float, steps: int = 8
) -> list[tuple[float, float]]:
    """The target broken into equal-ratio rungs.

    Compounding is multiplicative, so equal *ratios* are equal work: $100 to
    $316 is exactly as hard as $316,000 to $1,000,000. Showing the ladder this
    way makes the shape of the problem visible — the last rung is not the hard
    one, they all are.
    """
    if start_usd <= 0 or target_usd <= start_usd:
        return []
    ratio = (target_usd / start_usd) ** (1 / steps)
    rungs = []
    level = start_usd
    for _ in range(steps):
        nxt = level * ratio
        rungs.append((level, nxt))
        level = nxt
    return rungs


def r_multiples_from_trades(trades: Iterable, stop_loss_pct: float) -> list[float]:
    """Convert closed trades into R-multiples using the configured stop.

    One R is what a trade was supposed to lose if it hit its stop, so a
    ``ClosedTrade`` returning -30% with a 30% stop is -1R. This is what lets
    realised results be fed back into the growth math on the same axis the
    assumptions were stated on.
    """
    if stop_loss_pct <= 0:
        raise ValueError("stop_loss_pct must be positive")
    return [t.return_pct / stop_loss_pct for t in trades]


def minimum_viable_equity(
    distribution: TradeDistribution,
    min_position_usd: float,
    stop_loss_pct: float,
    kelly_fraction: float = 1.0,
) -> float:
    """The smallest account that can bet growth-optimally at all.

    A position sized to risk ``f`` of equity across a ``stop_loss_pct`` stop is
    ``equity * f / stop_loss_pct`` in size. Gas and DEX minimums put a floor
    under that size, so below a certain equity the smallest trade you can place
    risks *more* than the growth-optimal fraction — the account is structurally
    forced to overbet, and no discipline fixes it.

    This is the number that actually answers "can I start with $100": if it
    comes back above the starting capital, the honest answer is no, and the
    fix is more capital or a strategy with a fatter tail, not more trading.
    """
    optimal = distribution.optimal_fraction() * kelly_fraction
    if optimal <= 0:
        return float("inf")
    return min_position_usd * stop_loss_pct / optimal


def stall_equity(
    fraction: float, min_position_usd: float, stop_loss_pct: float
) -> float:
    """Equity below which no valid trade can be placed at all.

    Risking ``fraction`` across a ``stop_loss_pct`` stop buys a position of
    ``equity * fraction / stop_loss_pct``. Set that equal to the minimum
    position and solve: below this equity the desk is not losing, it is
    finished. On a $100 account with the shipped defaults this sits at $75,
    which means the account has a 25% drawdown of room before it stops being
    able to trade — a much tighter budget than the equity floor suggests.
    """
    if fraction <= 0:
        return float("inf")
    return min_position_usd * stop_loss_pct / fraction


def tail_sensitivity(
    distribution: TradeDistribution,
    fraction: float,
    tail_multiples: Sequence[float] = (10, 18, 25, 40, 60, 100),
) -> list[dict]:
    """How the whole picture moves with the size of the biggest winner.

    In this asset class one number dominates everything: how large the rare
    runner is. It is also the number nobody can know in advance, which is why
    this is reported as a range rather than a forecast. The largest-R outcome
    in the distribution is swapped out and everything else held fixed.
    """
    if not distribution.outcomes:
        return []
    tail_index = max(
        range(len(distribution.outcomes)),
        key=lambda i: distribution.outcomes[i].r_multiple,
    )
    rows = []
    for tail in tail_multiples:
        outcomes = list(distribution.outcomes)
        original = outcomes[tail_index]
        outcomes[tail_index] = Outcome(original.probability, tail, original.label)
        variant = TradeDistribution(tuple(outcomes))
        rows.append(
            {
                "tail_r": tail,
                "expectancy_r": variant.expectancy_r,
                "kelly_fraction": variant.optimal_fraction(),
                "log_growth": variant.log_growth_per_trade(fraction),
                "survivable": variant.log_growth_per_trade(fraction) > 0,
            }
        )
    return rows
