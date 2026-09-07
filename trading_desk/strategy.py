"""Entry scoring and exit rules.

The edge this strategy claims is narrow and worth stating plainly: memecoin
price action is driven by attention, attention arrives in bursts, and a burst
in progress is briefly measurable — rising price on rising participation, in a
pool deep enough to get out of. That is all this scores. It has no view on
whether a token is good, and no ability to see a rug coming.

The exit rules carry more of the expected value than the entry score does. A
strategy whose losers are cut at a fixed fraction and whose winners are allowed
to run can be profitable while being wrong most of the time, which is the only
shape that fits this asset class.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from .config import StrategyConfig
from .models import Candidate, ExitReason, Pair, Position, SafetyVerdict

# Weights for the composite entry score. They sum to 1.0 so the score is
# directly comparable to StrategyConfig.min_entry_score.
WEIGHTS = {
    "momentum_1h": 0.28,
    "momentum_5m": 0.17,
    "volume_acceleration": 0.22,
    "buy_pressure": 0.18,
    "depth": 0.10,
    "freshness": 0.05,
}


def _saturate(value: float, scale: float) -> float:
    """Map [0, inf) onto [0, 1) with diminishing returns above ``scale``.

    Used so that a +300% hour does not score fifteen times better than a +20%
    hour: past a point, more is not more, it is just later.
    """
    if value <= 0:
        return 0.0
    return value / (value + scale)


@dataclass
class ExitDecision:
    reason: ExitReason
    fraction: float  # of the *current* remaining quantity
    note: str

    @property
    def is_full(self) -> bool:
        return self.fraction >= 0.999


def score_momentum_1h(pair: Pair) -> Optional[float]:
    if pair.change_1h is None:
        return None
    return _saturate(pair.change_1h, 0.35)


def score_momentum_5m(pair: Pair, cfg: StrategyConfig) -> Optional[float]:
    """Reward a live 5-minute push, but fade it once it looks like a blow-off.

    Buying a candle already up 80% in five minutes means buying from whoever
    is about to sell into you, so the score falls away as the move approaches
    ``max_change_5m`` rather than rising all the way to the rejection line.
    """
    if pair.change_5m is None:
        return None
    if pair.change_5m <= 0:
        return 0.0
    raw = _saturate(pair.change_5m, 0.08)
    overheat = pair.change_5m / cfg.max_change_5m if cfg.max_change_5m > 0 else 0.0
    if overheat > 0.5:
        raw *= max(0.0, 1.0 - (overheat - 0.5) * 2)
    return raw


def score_volume_acceleration(pair: Pair) -> Optional[float]:
    """Is the current five-minute run-rate above the trailing hourly rate?

    ``volume_5m * 12`` is the hour that the last five minutes implies. Divided
    by actual 1h volume, values above 1 mean participation is picking up right
    now, which is what separates a burst starting from a burst ending.
    """
    if pair.volume_5m is None or not pair.volume_1h:
        return None
    implied_hourly = pair.volume_5m * 12.0
    ratio = implied_hourly / pair.volume_1h
    return _saturate(ratio, 1.5)


def score_buy_pressure(pair: Pair) -> Optional[float]:
    """Blend the 5m and 1h buy share, centred so 50/50 scores zero."""
    ratios = [r for r in (pair.txns_5m.buy_ratio, pair.txns_1h.buy_ratio) if r is not None]
    if not ratios:
        return None
    weighted = (
        ratios[0]
        if len(ratios) == 1
        else 0.6 * ratios[0] + 0.4 * ratios[1]
    )
    return max(0.0, min(1.0, (weighted - 0.5) * 2.5))


def score_depth(pair: Pair) -> Optional[float]:
    """Deeper pools score higher: they are what make an exit possible."""
    if not pair.liquidity_usd or pair.liquidity_usd <= 0:
        return None
    # $15k -> ~0.0, $100k -> ~0.5, $1M -> ~0.87 on a log scale.
    return max(0.0, min(1.0, (math.log10(pair.liquidity_usd) - 4.18) / 1.8))


def score_freshness(pair: Pair) -> Optional[float]:
    """Peak score for pools hours old, decaying over days.

    The window this strategy trades closes fast: by day three, whoever was
    going to hear about the token has heard about it.
    """
    age = pair.age_minutes
    if age is None:
        return None
    hours = age / 60.0
    if hours <= 6:
        return 1.0
    return max(0.0, 1.0 - (hours - 6) / 66.0)  # zero at ~3 days


def evaluate_entry(
    pair: Pair, safety: SafetyVerdict, cfg: StrategyConfig
) -> Candidate:
    """Score a pair and decide whether it is a buy right now.

    A component the data cannot answer is dropped and its weight redistributed
    across the rest, so a feed that omits 5-minute volume produces a slightly
    less informed score rather than an artificially low one. If too little is
    known to judge at all, the candidate is rejected outright.
    """
    components: dict[str, float] = {}
    raw = {
        "momentum_1h": score_momentum_1h(pair),
        "momentum_5m": score_momentum_5m(pair, cfg),
        "volume_acceleration": score_volume_acceleration(pair),
        "buy_pressure": score_buy_pressure(pair),
        "depth": score_depth(pair),
        "freshness": score_freshness(pair),
    }
    available = {k: v for k, v in raw.items() if v is not None}
    rejections: list[str] = []

    total_weight = sum(WEIGHTS[k] for k in available)
    if total_weight < 0.5:
        rejections.append("not enough market data to score this pair")
        score = 0.0
    else:
        score = sum(WEIGHTS[k] * v for k, v in available.items()) / total_weight
        components = dict(available)

    if pair.change_1h is None:
        rejections.append("1h price change unknown")
    elif pair.change_1h < cfg.min_change_1h:
        rejections.append(
            f"1h change {pair.change_1h * 100:+.1f}% is under the "
            f"{cfg.min_change_1h * 100:+.1f}% entry threshold"
        )
    if pair.change_5m is not None and pair.change_5m > cfg.max_change_5m:
        rejections.append(
            f"5m change {pair.change_5m * 100:+.0f}% is a blow-off; not chasing"
        )
    if not rejections and score < cfg.min_entry_score:
        rejections.append(f"score {score:.2f} below entry threshold {cfg.min_entry_score:.2f}")

    return Candidate(
        pair=pair,
        safety=safety,
        score=score,
        components=components,
        rejections=rejections,
    )


def initial_stop_price(entry_price: float, cfg: StrategyConfig) -> float:
    return entry_price * (1 - cfg.stop_loss_pct)


def update_position_marks(position: Position, pair: Optional[Pair]) -> None:
    """Fold the latest quote into the position's tracked state.

    The high-water mark only ever moves up; it is what the trailing stop hangs
    from, so a single bad quote must not be able to reset it.
    """
    if pair is None or not pair.price_usd:
        return
    position.last_price = pair.price_usd
    if pair.liquidity_usd is not None:
        position.last_liquidity_usd = pair.liquidity_usd
    if pair.price_usd > position.high_water_price:
        position.high_water_price = pair.price_usd


def trailing_stop_price(position: Position, cfg: StrategyConfig) -> Optional[float]:
    if not position.trailing_armed:
        return None
    return position.high_water_price * (1 - cfg.trail_giveback_pct)


def evaluate_exit(
    position: Position, pair: Optional[Pair], cfg: StrategyConfig
) -> Optional[ExitDecision]:
    """Decide what, if anything, to sell out of an open position.

    Checks run in order of urgency. Liquidity drain comes first because it is
    the only condition where the exit itself may stop being possible: every
    other rule can wait a tick, that one cannot.
    """
    price = position.last_price
    if not price:
        return None

    # 1. The pool is being pulled out from under the position.
    if (
        position.entry_liquidity_usd
        and position.last_liquidity_usd is not None
        and position.entry_liquidity_usd > 0
    ):
        drop = 1 - position.last_liquidity_usd / position.entry_liquidity_usd
        if drop >= cfg.liquidity_drain_pct:
            return ExitDecision(
                ExitReason.LIQUIDITY_DRAIN,
                1.0,
                f"pool depth down {drop * 100:.0f}% since entry",
            )

    # 2. Hard stop.
    if price <= position.stop_price:
        return ExitDecision(
            ExitReason.STOP_LOSS,
            1.0,
            f"price ${price:.8g} hit stop ${position.stop_price:.8g}",
        )

    # 3. Trailing stop, once the position has earned one.
    if position.multiple >= cfg.trail_arm_multiple:
        position.trailing_armed = True
    trail = trailing_stop_price(position, cfg)
    if trail is not None and price <= trail:
        return ExitDecision(
            ExitReason.TRAILING_STOP,
            1.0,
            f"gave back {cfg.trail_giveback_pct * 100:.0f}% from the ${position.high_water_price:.8g} high",
        )

    # 4. Scale-out ladder — bank size into strength, in original-position terms.
    level_index = position.scale_outs_done
    if level_index < len(cfg.scale_out_levels):
        level = cfg.scale_out_levels[level_index]
        if position.multiple >= level:
            target_qty = position.initial_quantity * cfg.scale_out_fractions[level_index]
            fraction = min(1.0, target_qty / position.quantity) if position.quantity else 0.0
            if fraction > 0:
                return ExitDecision(
                    ExitReason.TAKE_PROFIT,
                    fraction,
                    f"scaling out {cfg.scale_out_fractions[level_index] * 100:.0f}% at {level:.1f}x",
                )

    # 5. The move is over.
    if pair is not None and pair.change_1h is not None and pair.change_1h <= cfg.momentum_dead_change_1h:
        return ExitDecision(
            ExitReason.MOMENTUM_DEAD,
            1.0,
            f"1h change {pair.change_1h * 100:+.0f}% — the move is done",
        )

    # 6. Capital that is not working should be somewhere else.
    if (
        position.age_minutes >= cfg.time_stop_minutes
        and position.multiple < cfg.time_stop_min_multiple
    ):
        return ExitDecision(
            ExitReason.TIME_STOP,
            1.0,
            f"flat at {position.multiple:.2f}x after {position.age_minutes:.0f}m",
        )

    return None


def apply_post_exit_adjustments(position: Position, decision: ExitDecision, cfg: StrategyConfig) -> None:
    """Tighten the stop after banking a tranche.

    Once the first scale-out is done the trade has paid for part of itself, so
    the stop moves to entry: from that point the remaining size cannot turn a
    booked win into a loss.
    """
    if decision.reason is not ExitReason.TAKE_PROFIT:
        return
    position.scale_outs_done += 1
    if position.scale_outs_done >= 1:
        position.stop_price = max(position.stop_price, position.avg_entry_price)
