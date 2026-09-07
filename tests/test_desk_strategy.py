"""Entry scoring and, more importantly, the exit rules."""
import time

import pytest

from tests.factories import make_hot_pair, make_pair
from trading_desk.config import StrategyConfig
from trading_desk.models import Chain, ExitReason, Position, SafetyVerdict, TxnCounts
from trading_desk.strategy import (
    apply_post_exit_adjustments,
    evaluate_entry,
    evaluate_exit,
    initial_stop_price,
    update_position_marks,
)

CLEAN = SafetyVerdict(passed=True, score=100)


@pytest.fixture
def cfg():
    return StrategyConfig()


def make_position(**overrides) -> Position:
    defaults = dict(
        chain=Chain.SOLANA,
        token_address="TOKEN1",
        symbol="DOGE",
        quantity=10_000.0,
        avg_entry_price=0.001,
        cost_basis_usd=10.0,
        stop_price=0.0007,
        entry_liquidity_usd=120_000.0,
        last_liquidity_usd=120_000.0,
    )
    defaults.update(overrides)
    return Position(**defaults)


# ------------------------------------------------------------------- entries


def test_strong_setup_is_tradeable(cfg, hot_pair):
    candidate = evaluate_entry(hot_pair, CLEAN, cfg)
    assert candidate.tradeable
    assert candidate.score >= cfg.min_entry_score


def test_mediocre_setup_is_scored_but_not_taken(cfg, pair):
    candidate = evaluate_entry(pair, CLEAN, cfg)
    assert not candidate.tradeable
    assert 0 < candidate.score < cfg.min_entry_score


def test_falling_hour_is_rejected_regardless_of_score(cfg):
    candidate = evaluate_entry(make_hot_pair(change_1h=-0.10), CLEAN, cfg)
    assert not candidate.tradeable
    assert any("entry threshold" in r for r in candidate.rejections)


def test_blow_off_candle_is_not_chased(cfg):
    candidate = evaluate_entry(make_hot_pair(change_5m=3.0), CLEAN, cfg)
    assert not candidate.tradeable
    assert any("blow-off" in r for r in candidate.rejections)


def test_overheated_5m_scores_lower_than_a_steady_push(cfg):
    steady = evaluate_entry(make_hot_pair(change_5m=0.10), CLEAN, cfg)
    overheated = evaluate_entry(make_hot_pair(change_5m=0.85), CLEAN, cfg)
    assert overheated.components["momentum_5m"] < steady.components["momentum_5m"]


def test_missing_components_redistribute_weight_rather_than_scoring_zero(cfg):
    """A feed that omits 5m volume should not silently penalise the token."""
    full = evaluate_entry(make_hot_pair(), CLEAN, cfg)
    partial = evaluate_entry(make_hot_pair(volume_5m=None), CLEAN, cfg)
    assert "volume_acceleration" not in partial.components
    assert partial.score == pytest.approx(full.score, abs=0.2)


def test_too_little_data_is_rejected_outright(cfg):
    barren = make_pair(
        change_1h=None,
        change_5m=None,
        volume_5m=None,
        volume_1h=None,
        txns_5m=TxnCounts(),
        txns_1h=TxnCounts(),
        liquidity_usd=None,
        created_at=None,
    )
    candidate = evaluate_entry(barren, CLEAN, cfg)
    assert not candidate.tradeable
    assert candidate.score == 0.0


# --------------------------------------------------------------------- exits


def test_no_exit_while_the_trade_is_working(cfg):
    position = make_position(last_price=0.0012)
    assert evaluate_exit(position, make_pair(price_usd=0.0012), cfg) is None


def test_hard_stop_fires(cfg):
    position = make_position(last_price=0.0006)
    decision = evaluate_exit(position, make_pair(price_usd=0.0006), cfg)
    assert decision.reason is ExitReason.STOP_LOSS
    assert decision.is_full


def test_liquidity_drain_outranks_everything(cfg):
    """Even a position in profit exits when the pool is being pulled."""
    position = make_position(last_price=0.0025, last_liquidity_usd=50_000.0)
    decision = evaluate_exit(position, make_pair(price_usd=0.0025), cfg)
    assert decision.reason is ExitReason.LIQUIDITY_DRAIN
    assert decision.is_full


def test_scale_out_ladder_sells_a_fraction_at_each_level(cfg):
    position = make_position(last_price=0.002)  # 2x
    decision = evaluate_exit(position, make_pair(price_usd=0.002), cfg)
    assert decision.reason is ExitReason.TAKE_PROFIT
    assert decision.fraction == pytest.approx(cfg.scale_out_fractions[0])


def test_scale_out_fractions_are_of_the_original_position(cfg):
    """After the first tranche, 30% of the original is a larger share of what's left."""
    position = make_position(quantity=6_000.0, initial_quantity=10_000.0, scale_outs_done=1)
    position.last_price = 0.004  # 4x
    decision = evaluate_exit(position, make_pair(price_usd=0.004), cfg)
    expected = 10_000.0 * cfg.scale_out_fractions[1] / 6_000.0
    assert decision.fraction == pytest.approx(expected)


def test_first_scale_out_moves_the_stop_to_breakeven(cfg):
    position = make_position(last_price=0.002)
    decision = evaluate_exit(position, make_pair(price_usd=0.002), cfg)
    apply_post_exit_adjustments(position, decision, cfg)
    assert position.scale_outs_done == 1
    assert position.stop_price == pytest.approx(position.avg_entry_price)


def test_trailing_stop_arms_then_fires_on_giveback(cfg):
    position = make_position()
    update_position_marks(position, make_pair(price_usd=0.002))  # 2x, arms the trail
    assert evaluate_exit(position, make_pair(price_usd=0.002), cfg).reason is ExitReason.TAKE_PROFIT
    position.scale_outs_done = 3  # ladder exhausted, only the trail is left

    update_position_marks(position, make_pair(price_usd=0.0014))
    decision = evaluate_exit(position, make_pair(price_usd=0.0014), cfg)
    assert decision.reason is ExitReason.TRAILING_STOP


def test_high_water_mark_only_moves_up(cfg):
    position = make_position()
    update_position_marks(position, make_pair(price_usd=0.003))
    update_position_marks(position, make_pair(price_usd=0.0015))
    assert position.high_water_price == pytest.approx(0.003)


def test_time_stop_closes_a_position_going_nowhere(cfg):
    position = make_position(
        last_price=0.00102, opened_at=time.time() - (cfg.time_stop_minutes + 10) * 60
    )
    decision = evaluate_exit(position, make_pair(price_usd=0.00102), cfg)
    assert decision.reason is ExitReason.TIME_STOP


def test_time_stop_spares_a_position_that_is_working(cfg):
    position = make_position(
        last_price=0.0018, opened_at=time.time() - (cfg.time_stop_minutes + 10) * 60
    )
    assert evaluate_exit(position, make_pair(price_usd=0.0018), cfg) is None


def test_dead_momentum_closes_the_trade(cfg):
    position = make_position(last_price=0.0011)
    decision = evaluate_exit(position, make_pair(price_usd=0.0011, change_1h=-0.4), cfg)
    assert decision.reason is ExitReason.MOMENTUM_DEAD


def test_initial_stop_sits_below_entry(cfg):
    assert initial_stop_price(0.001, cfg) == pytest.approx(0.0007)
