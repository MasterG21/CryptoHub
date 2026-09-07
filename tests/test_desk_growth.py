"""The compounding math behind the $100 -> $1,000,000 target."""
import math

import pytest

from trading_desk.growth import (
    DEFAULT_DISTRIBUTION,
    GrowthMath,
    Outcome,
    TradeDistribution,
    milestone_ladder,
    minimum_viable_equity,
    r_multiples_from_trades,
    simulate,
    tail_sensitivity,
)


def test_probabilities_must_sum_to_one():
    with pytest.raises(ValueError, match="sum to"):
        TradeDistribution((Outcome(0.5, 1.0), Outcome(0.2, -1.0)))


def test_expectancy_and_win_rate():
    dist = TradeDistribution((Outcome(0.5, 2.0), Outcome(0.5, -1.0)))
    assert dist.expectancy_r == pytest.approx(0.5)
    assert dist.win_rate == pytest.approx(0.5)


def test_a_bet_that_can_zero_the_account_has_no_growth_rate():
    """f * worst-case = -1 wipes out; log growth is -inf, not merely bad."""
    dist = TradeDistribution((Outcome(0.5, 2.0), Outcome(0.5, -1.0)))
    assert dist.log_growth_per_trade(1.0) == float("-inf")


def test_kelly_matches_the_closed_form_for_a_coin_flip():
    """Even-odds 2:1 with p=0.5 has a known optimum of 25%."""
    dist = TradeDistribution((Outcome(0.5, 2.0), Outcome(0.5, -1.0)))
    assert dist.optimal_fraction() == pytest.approx(0.25, abs=0.01)


def test_overbetting_reduces_growth_as_well_as_raising_risk():
    dist = TradeDistribution((Outcome(0.5, 2.0), Outcome(0.5, -1.0)))
    optimal = dist.optimal_fraction()
    assert dist.log_growth_per_trade(optimal * 2.5) < dist.log_growth_per_trade(optimal)


def test_positive_expectancy_can_still_compound_downward():
    """The whole point: arithmetic edge does not imply survival."""
    assert DEFAULT_DISTRIBUTION.expectancy_r > 0
    assert DEFAULT_DISTRIBUTION.log_growth_per_trade(0.06) < 0


def test_unreachable_target_reports_none_rather_than_a_huge_number():
    math_ = GrowthMath(100, 1_000_000, 0.06, DEFAULT_DISTRIBUTION)
    assert math_.trades_required is None
    assert math_.days_required(10) is None
    assert math_.overbet


def test_reachable_target_reports_the_trade_count():
    dist = TradeDistribution((Outcome(0.5, 2.0), Outcome(0.5, -1.0)))
    math_ = GrowthMath(100, 1_000_000, 0.25, dist)
    expected = math.log(10_000) / dist.log_growth_per_trade(0.25)
    assert math_.trades_required == pytest.approx(expected)
    assert math_.days_required(5) == pytest.approx(expected / 5)


def test_minimum_viable_equity_reflects_the_position_floor():
    """A $5 minimum across a 30% stop cannot be a 0.33% bet on $100."""
    viable = minimum_viable_equity(DEFAULT_DISTRIBUTION, 5.0, 0.30)
    assert viable > 100
    assert viable == pytest.approx(5.0 * 0.30 / DEFAULT_DISTRIBUTION.optimal_fraction())


def test_tail_sensitivity_shows_where_survival_begins():
    rows = tail_sensitivity(DEFAULT_DISTRIBUTION, 0.02)
    assert not rows[0]["survivable"]  # a 10R best case is not enough
    assert rows[-1]["survivable"]  # a 100R runner is
    assert rows[0]["kelly_fraction"] <= rows[-1]["kelly_fraction"]


def test_milestone_ladder_rungs_are_equal_ratios():
    rungs = milestone_ladder(100, 1_000_000, steps=4)
    ratios = [high / low for low, high in rungs]
    assert len(rungs) == 4
    assert all(r == pytest.approx(ratios[0]) for r in ratios)
    assert rungs[-1][1] == pytest.approx(1_000_000)


def test_milestone_ladder_rejects_impossible_ranges():
    assert milestone_ladder(100, 50) == []
    assert milestone_ladder(0, 1000) == []


# ---------------------------------------------------------------- simulation


def test_simulation_is_deterministic_for_a_given_seed():
    a = simulate(runs=200, trades=200, seed=42)
    b = simulate(runs=200, trades=200, seed=42)
    assert a.terminal_equity == b.terminal_equity


def test_overbetting_the_default_distribution_mostly_kills_the_account():
    result = simulate(runs=1000, trades=1000, fraction=0.06, seed=1)
    assert result.p_dead > 0.9
    assert result.p_target < 0.01


def test_an_account_too_small_to_place_a_trade_counts_as_dead_not_neutral():
    """Stalling at $24 with a $5 minimum is not a survival — it is an ending."""
    result = simulate(runs=200, trades=500, fraction=0.06, min_position_usd=5.0, seed=1)
    assert result.p_stalled > 0
    assert result.p_dead == pytest.approx(result.p_ruin + result.p_stalled)

    # A run that stalls has stopped above the ruin floor but below the equity
    # that could fund another minimum position, and it stays there.
    stall_ceiling = 5.0 * 0.30 / 0.06
    assert any(15.0 < e < stall_ceiling for e in result.terminal_equity)


def test_a_genuinely_good_edge_reaches_the_target():
    dist = TradeDistribution((Outcome(0.5, 2.0), Outcome(0.5, -1.0)))
    result = simulate(runs=500, trades=5000, fraction=0.25, distribution=dist, seed=3)
    assert result.p_target > 0.5


def test_the_mean_outruns_the_median_in_a_fat_tailed_book():
    result = simulate(runs=2000, trades=800, fraction=0.02, seed=5)
    assert result.mean_equity > result.median_equity


def test_a_run_stops_once_it_falls_through_the_ruin_floor():
    result = simulate(runs=200, trades=2000, fraction=0.5, ruin_floor_usd=15.0, seed=9)
    assert all(e <= 15.0 or e >= 1_000_000 for e in result.terminal_equity)


def test_percentiles_are_ordered():
    result = simulate(runs=500, trades=500, seed=11)
    assert result.percentile(5) <= result.median_equity <= result.percentile(95)


# ------------------------------------------------------- feeding results back


class _Trade:
    def __init__(self, return_pct):
        self.return_pct = return_pct


def test_realised_trades_convert_to_r_multiples():
    """A -30% result against a 30% stop is exactly -1R."""
    r = r_multiples_from_trades([_Trade(-0.30), _Trade(0.60)], stop_loss_pct=0.30)
    assert r == pytest.approx([-1.0, 2.0])


def test_an_empirical_distribution_can_be_rebuilt_from_trades():
    r_multiples = [-1.0] * 60 + [0.5] * 20 + [3.0] * 15 + [20.0] * 5
    dist = TradeDistribution.from_trades(r_multiples, buckets=4)
    assert sum(o.probability for o in dist.outcomes) == pytest.approx(1.0)
    assert dist.expectancy_r == pytest.approx(sum(r_multiples) / len(r_multiples), rel=1e-6)


def test_building_a_distribution_needs_trades():
    with pytest.raises(ValueError, match="no trades"):
        TradeDistribution.from_trades([])


def test_stall_equity_marks_where_trading_becomes_impossible():
    """$5 minimum, 30% stop, 2% risk: below $75 there is no valid trade."""
    from trading_desk.growth import stall_equity

    assert stall_equity(0.02, 5.0, 0.30) == pytest.approx(75.0)
    assert stall_equity(0.10, 5.0, 0.30) == pytest.approx(15.0)  # bigger bets stall later
    assert stall_equity(0.0, 5.0, 0.30) == float("inf")
