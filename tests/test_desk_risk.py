"""Position sizing caps and the circuit breakers."""
import pytest

from tests.factories import make_pair
from trading_desk.config import RiskConfig
from trading_desk.models import Chain
from trading_desk.risk import RiskManager, RiskState, size_position


@pytest.fixture
def cfg():
    return RiskConfig()


def test_risk_cap_binds_on_a_deep_pool(cfg):
    """$100 risking 2% across a 30% stop is a $6.67 position."""
    result = size_position(100, 100, 0.001, 0.0007, make_pair(liquidity_usd=500_000), cfg)
    assert result.ok
    assert result.binding_constraint == "risk"
    assert result.usd_amount == pytest.approx(100 * 0.02 / 0.3, abs=0.01)


def test_pool_impact_cap_binds_on_a_thin_pool(cfg):
    """The pool, not the account, is what limits size on a small pool."""
    result = size_position(10_000, 10_000, 0.001, 0.0007, make_pair(liquidity_usd=20_000), cfg)
    assert result.binding_constraint == "pool_impact"
    assert result.usd_amount == pytest.approx(20_000 * cfg.max_pool_impact_pct)


def test_position_cap_binds_when_the_stop_is_tight(cfg):
    result = size_position(1_000, 1_000, 0.001, 0.00098, make_pair(liquidity_usd=5_000_000), cfg)
    assert result.binding_constraint == "position"
    assert result.usd_amount == pytest.approx(1_000 * cfg.max_position_pct)


def test_cash_reserve_is_never_deployed(cfg):
    result = size_position(1_000, 100, 0.001, 0.0007, make_pair(liquidity_usd=5_000_000), cfg)
    assert result.binding_constraint == "cash"
    assert result.usd_amount == pytest.approx(100 - 1_000 * cfg.cash_reserve_pct)


def test_dust_sized_positions_are_refused(cfg):
    """Below the minimum, gas and fees eat the trade before it starts."""
    result = size_position(20, 20, 0.001, 0.0007, make_pair(liquidity_usd=200_000), cfg)
    assert not result.ok
    assert "minimum" in result.rejected_reason


def test_unknown_liquidity_refuses_to_size(cfg):
    result = size_position(100, 100, 0.001, 0.0007, make_pair(liquidity_usd=None), cfg)
    assert not result.ok
    assert "unknown" in result.rejected_reason


def test_stop_must_sit_below_entry(cfg):
    result = size_position(100, 100, 0.001, 0.0012, make_pair(), cfg)
    assert not result.ok
    assert "below the entry" in result.rejected_reason


# ------------------------------------------------------------------- breakers


def test_daily_loss_limit_halts_new_entries(cfg):
    manager = RiskManager(cfg)
    manager.sync_day(100)
    assert manager.check_halt(90) is None
    assert "daily loss limit" in manager.check_halt(70)


def test_equity_floor_halts_trading(cfg):
    manager = RiskManager(cfg)
    manager.sync_day(100)
    assert "floor" in manager.check_halt(cfg.equity_floor_usd - 1)


def test_losing_streak_halts_trading(cfg):
    manager = RiskManager(cfg)
    manager.sync_day(100)
    for _ in range(cfg.max_consecutive_losses):
        manager.state.record_close(-2.0)
    assert "in a row" in manager.check_halt(95)


def test_a_win_resets_the_losing_streak(cfg):
    manager = RiskManager(cfg)
    manager.sync_day(100)
    for _ in range(cfg.max_consecutive_losses):
        manager.state.record_close(-2.0)
    manager.state.record_close(5.0)
    assert manager.state.consecutive_losses == 0
    assert manager.check_halt(95) is None


def test_day_roll_clears_the_daily_halt_but_not_the_streak():
    state = RiskState(day="2020-01-01", day_start_equity=100.0, consecutive_losses=4)
    state.halted_reason = "down 30.0% today, past the daily loss limit"
    assert state.roll_day(70.0, now=0)  # 1970-01-01, a different day
    assert state.halted_reason is None
    assert state.day_start_equity == 70.0
    assert state.consecutive_losses == 4


def test_capacity_and_per_chain_limits(cfg):
    manager = RiskManager(cfg)

    class P:
        def __init__(self, chain):
            self.chain = chain

    positions = [P(Chain.SOLANA), P(Chain.SOLANA)]
    assert manager.capacity(positions) == cfg.max_concurrent_positions - 2
    assert not manager.chain_has_room(Chain.SOLANA, positions)
    assert manager.chain_has_room(Chain.BNB, positions)
