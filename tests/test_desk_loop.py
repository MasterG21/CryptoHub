"""End-to-end ticks of the desk against a fake feed — no network."""
import time

import pytest

from tests.factories import FakeFeed, make_hot_pair
from trading_desk.config import DeskConfig
from trading_desk.desk import TradingDesk
from trading_desk.execution.paper import PaperExecutor
from trading_desk.marketdata.base import MultiChainFeed
from trading_desk.models import Chain


def build_desk(pairs, **config_overrides):
    cfg = DeskConfig(**config_overrides)
    cfg.chains = (Chain.SOLANA,)
    feed = FakeFeed(pairs=pairs)
    desk = TradingDesk(
        config=cfg,
        feed=MultiChainFeed([feed]),
        executor=PaperExecutor(cfg),
        journal=None,
    )
    return desk, feed


def test_a_strong_candidate_is_bought(hot_pair):
    desk, _ = build_desk([hot_pair])
    result = desk.tick()

    assert len(result.entries) == 1
    assert desk.portfolio.holds(Chain.SOLANA, "TOKEN1")
    assert desk.portfolio.cash_usd < 100


def test_a_weak_candidate_is_left_alone(pair):
    desk, _ = build_desk([pair])
    result = desk.tick()

    assert result.entries == []
    assert result.scored == 1
    assert not desk.portfolio.positions


def test_an_unsafe_candidate_never_reaches_scoring():
    desk, _ = build_desk([make_hot_pair(liquidity_usd=2_000)])
    result = desk.tick()

    assert result.safety_rejected == 1
    assert result.scored == 0
    assert result.entries == []


def test_a_stopped_out_position_is_sold_on_the_next_tick(hot_pair):
    desk, feed = build_desk([hot_pair])
    desk.tick()
    assert desk.portfolio.holds(Chain.SOLANA, "TOKEN1")

    feed.set_price("TOKEN1", 0.0005)  # through the 30% stop
    result = desk.tick()

    assert any("stop-loss" in e for e in result.exits)
    assert not desk.portfolio.positions
    assert desk.portfolio.closed_trades[0].pnl_usd < 0


def test_a_winner_scales_out_and_keeps_running(hot_pair):
    desk, feed = build_desk([hot_pair])
    desk.tick()
    position = desk.portfolio.open_positions[0]
    original_quantity = position.quantity

    feed.set_price("TOKEN1", 0.0022)  # clear of the 2x rung, entry slippage included
    result = desk.tick()

    assert any("take-profit" in e for e in result.exits)
    assert 0 < position.quantity < original_quantity
    assert position.stop_price == pytest.approx(position.avg_entry_price)


def test_exits_still_run_while_entries_are_halted(hot_pair):
    """A circuit breaker must never trap the desk in a losing position."""
    desk, feed = build_desk([hot_pair])
    desk.tick()
    desk.risk.state.consecutive_losses = 99  # trip the breaker

    feed.set_price("TOKEN1", 0.0005)
    result = desk.tick()

    assert result.halted_reason is not None
    assert any("stop-loss" in e for e in result.exits)
    assert not desk.portfolio.positions


def test_halted_desk_opens_nothing_new(hot_pair):
    desk, _ = build_desk([hot_pair])
    desk.risk.state.consecutive_losses = 99
    result = desk.tick()

    assert result.halted_reason is not None
    assert result.entries == []


def test_position_limits_cap_concurrent_exposure():
    pairs = [
        make_hot_pair(base_address=f"TOKEN{i}", base_symbol=f"T{i}", pair_address=f"POOL{i}")
        for i in range(6)
    ]
    desk, _ = build_desk(pairs)
    desk.config.risk.max_positions_per_chain = 2
    result = desk.tick()

    assert len(result.entries) == 2
    assert len(desk.portfolio.open_positions) == 2


def test_the_same_token_is_not_bought_twice(hot_pair):
    desk, _ = build_desk([hot_pair])
    desk.tick()
    result = desk.tick()

    assert result.entries == []
    assert len(desk.portfolio.open_positions) == 1


def test_a_broken_feed_does_not_stop_the_tick():
    cfg = DeskConfig()
    cfg.chains = (Chain.SOLANA,)
    working = FakeFeed(chain=Chain.SOLANA, pairs=[make_hot_pair()])
    broken = FakeFeed(chain=Chain.BNB, fail=True)
    desk = TradingDesk(
        config=cfg,
        feed=MultiChainFeed([working, broken]),
        executor=PaperExecutor(cfg),
        journal=None,
    )
    result = desk.tick()

    assert any("feed is down" in e for e in result.errors)
    assert len(result.entries) == 1  # the healthy chain still traded


def test_a_position_with_no_fresh_quote_keeps_its_last_mark(hot_pair):
    desk, feed = build_desk([hot_pair])
    desk.tick()
    entry_value = desk.portfolio.positions_value_usd

    feed.pairs = []  # the token vanishes from the feed
    result = desk.tick()

    assert any("no fresh quote" in e for e in result.errors)
    assert desk.portfolio.positions_value_usd == pytest.approx(entry_value)


def test_liquidity_drain_forces_an_exit_even_at_a_profit(hot_pair):
    desk, feed = build_desk([hot_pair])
    desk.tick()

    feed.set_price("TOKEN1", 0.0015, liquidity=60_000)  # up 50%, pool halved
    result = desk.tick()

    assert any("liquidity-drain" in e for e in result.exits)
    assert not desk.portfolio.positions


def test_close_all_flattens_the_book(hot_pair):
    desk, _ = build_desk([hot_pair])
    desk.tick()
    assert desk.portfolio.positions

    closed = desk.close_all()
    assert len(closed) == 1
    assert not desk.portfolio.positions


def test_run_stops_after_max_ticks(hot_pair):
    desk, _ = build_desk([hot_pair])
    results = desk.run(max_ticks=3, sleep=lambda _: None)
    assert len(results) == 3


def test_a_crashing_tick_does_not_kill_the_loop(hot_pair, monkeypatch):
    desk, _ = build_desk([hot_pair])
    calls = {"n": 0}

    def exploding_tick():
        calls["n"] += 1
        raise RuntimeError("boom")

    monkeypatch.setattr(desk, "tick", exploding_tick)
    results = desk.run(max_ticks=2, sleep=lambda _: None)

    assert calls["n"] == 2
    assert all("boom" in r.errors[0] for r in results)


def test_progress_to_target_reports_the_gap(hot_pair):
    desk, _ = build_desk([hot_pair])
    progress = desk.progress_to_target()

    assert progress["starting_usd"] == 100.0
    assert progress["target_usd"] == 1_000_000.0
    assert progress["multiple_remaining"] == pytest.approx(10_000, rel=0.01)


def test_a_full_close_records_the_whole_line_once_for_the_streak_counter(hot_pair):
    """A scale-out then a stop must count as one trade, not a win and a loss."""
    desk, feed = build_desk([hot_pair])
    desk.tick()

    feed.set_price("TOKEN1", 0.0022)  # bank a tranche
    desk.tick()
    assert desk.risk.state.trades_today == 0  # partial exits don't count yet

    feed.set_price("TOKEN1", 0.0009)  # back through the breakeven stop
    desk.tick()

    assert not desk.portfolio.positions
    assert desk.risk.state.trades_today == 1


def test_a_token_is_not_bought_back_in_the_tick_it_stopped_out(hot_pair):
    """Momentum fields look fine the instant after a stop; the cooldown blocks it."""
    desk, feed = build_desk([hot_pair])
    desk.tick()

    feed.set_price("TOKEN1", 0.0005)
    result = desk.tick()

    assert any("stop-loss" in e for e in result.exits)
    assert result.entries == []
    assert not desk.portfolio.positions


def test_the_cooldown_expires_and_the_token_becomes_eligible_again(hot_pair):
    desk, feed = build_desk([hot_pair])
    desk.tick()
    feed.set_price("TOKEN1", 0.0005)
    desk.tick()
    assert not desk.portfolio.positions

    # Walk the desk's clock past the cooldown and restore a tradeable quote.
    desk.clock = lambda: time.time() + desk.config.strategy.reentry_cooldown_minutes * 60 + 1
    feed.set_price("TOKEN1", 0.001)
    result = desk.tick()

    assert len(result.entries) == 1
