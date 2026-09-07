"""Persistence: the desk must come back from a restart holding the same book."""
import os
import tempfile

import pytest


from trading_desk.config import DeskConfig
from trading_desk.execution.paper import PaperExecutor
from trading_desk.journal import Journal
from trading_desk.models import Chain, Order, Side
from trading_desk.portfolio import Portfolio
from trading_desk.risk import RiskState


@pytest.fixture
def journal_path():
    with tempfile.TemporaryDirectory() as directory:
        yield os.path.join(directory, "journal.sqlite3")


def open_a_position(portfolio, pair, usd=20.0):
    executor = PaperExecutor(DeskConfig())
    order = Order(
        chain=pair.chain,
        token_address=pair.base_address,
        symbol=pair.base_symbol,
        side=Side.BUY,
        usd_amount=usd,
        reference_price=pair.price_usd,
        pair=pair,
    )
    fill = executor.execute(order, pair)
    return fill, portfolio.apply_buy(fill, pair, stop_price=0.0007)


def test_cash_and_positions_survive_a_restart(journal_path, pair):
    portfolio = Portfolio(100.0)
    _, position = open_a_position(portfolio, pair)

    with Journal(journal_path) as journal:
        journal.save_state(portfolio, RiskState())

    with Journal(journal_path) as journal:
        restored = journal.load_portfolio(100.0)

    assert restored.cash_usd == pytest.approx(portfolio.cash_usd)
    assert len(restored.positions) == 1
    reloaded = restored.get(Chain.SOLANA, "TOKEN1")
    assert reloaded.quantity == pytest.approx(position.quantity)
    assert reloaded.stop_price == pytest.approx(position.stop_price)
    assert reloaded.initial_quantity == pytest.approx(position.initial_quantity)


def test_risk_counters_survive_a_restart(journal_path):
    """A restart must not hand the desk a fresh daily loss limit."""
    state = RiskState(day="2026-01-01", day_start_equity=100.0, consecutive_losses=3)
    state.realized_today_usd = -25.0

    with Journal(journal_path) as journal:
        journal.save_state(Portfolio(100.0), state)
    with Journal(journal_path) as journal:
        restored = journal.load_risk_state()

    assert restored.day == "2026-01-01"
    assert restored.consecutive_losses == 3
    assert restored.realized_today_usd == pytest.approx(-25.0)


def test_the_reentry_cooldown_survives_a_restart(journal_path):
    with Journal(journal_path) as journal:
        journal.save_state(Portfolio(100.0), RiskState(), {"solana:token1": 1234.5})
    with Journal(journal_path) as journal:
        assert journal.load_recent_exits() == {"solana:token1": 1234.5}


def test_closed_trades_are_reloaded_so_stats_stay_honest(journal_path, pair):
    portfolio = Portfolio(100.0)
    _, position = open_a_position(portfolio, pair)
    executor = PaperExecutor(DeskConfig())
    order = Order(
        chain=pair.chain,
        token_address=pair.base_address,
        symbol=pair.base_symbol,
        side=Side.SELL,
        quantity=position.quantity,
        reference_price=pair.price_usd,
        pair=pair,
    )
    trade = portfolio.apply_sell(executor.execute(order, pair), reason="stop-loss")

    with Journal(journal_path) as journal:
        journal.record_trade(trade)
        journal.save_state(portfolio, RiskState())
    with Journal(journal_path) as journal:
        restored = journal.load_portfolio(100.0)

    assert len(restored.closed_trades) == 1
    assert restored.closed_trades[0].reason == "stop-loss"
    assert restored.stats()["trades"] == 1


def test_saving_replaces_the_book_rather_than_appending(journal_path, pair):
    """A closed position must not linger in the database."""
    portfolio = Portfolio(100.0)
    open_a_position(portfolio, pair)

    with Journal(journal_path) as journal:
        journal.save_state(portfolio, RiskState())
        portfolio.positions.clear()
        journal.save_state(portfolio, RiskState())
        assert journal.load_portfolio(100.0).positions == {}


def test_fills_are_recorded_for_audit(journal_path, pair):
    portfolio = Portfolio(100.0)
    fill, _ = open_a_position(portfolio, pair)

    with Journal(journal_path) as journal:
        journal.record_fill(fill)
        rows = journal.conn.execute("SELECT * FROM fills").fetchall()

    assert len(rows) == 1
    assert rows[0]["side"] == "buy"
    assert rows[0]["slippage_pct"] > 0


def test_max_drawdown_reads_the_equity_curve(journal_path):
    portfolio = Portfolio(100.0)
    with Journal(journal_path) as journal:
        for equity, ts in ((100.0, 1.0), (150.0, 2.0), (75.0, 3.0), (120.0, 4.0)):
            portfolio.cash_usd = equity
            journal.snapshot_equity(portfolio, ts=ts)
        assert journal.max_drawdown_pct() == pytest.approx(0.5)  # 150 -> 75


def test_a_fresh_journal_starts_from_the_configured_capital(journal_path):
    with Journal(journal_path) as journal:
        portfolio = journal.load_portfolio(250.0)
    assert portfolio.cash_usd == 250.0
    assert portfolio.positions == {}


def test_starting_capital_is_remembered_not_re_read_from_config(journal_path):
    """Changing --capital mid-session must not rewrite the return history."""
    with Journal(journal_path) as journal:
        journal.save_state(Portfolio(100.0), RiskState())
    with Journal(journal_path) as journal:
        restored = journal.load_portfolio(999.0)
    assert restored.starting_cash_usd == 100.0


def test_the_journal_works_across_threads(journal_path):
    """The dashboard reads on HTTP threads while the desk writes on its own.

    SQLite connections default to refusing cross-thread use, which made every
    write from the desk thread fail silently in serve mode — no equity curve,
    and no restart safety.
    """
    import threading

    journal = Journal(journal_path)
    portfolio = Portfolio(100.0)
    errors = []

    def write():
        try:
            for i in range(20):
                portfolio.cash_usd = 100.0 + i
                journal.snapshot_equity(portfolio, ts=1000.0 + i)
                journal.save_state(portfolio, RiskState())
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    def read():
        try:
            for _ in range(20):
                journal.equity_curve()
                journal.load_risk_state()
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=write), threading.Thread(target=read)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert errors == []
    assert len(journal.equity_curve()) == 20
    journal.close()
