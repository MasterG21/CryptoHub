"""Cash, cost basis and P&L across partial exits."""
import pytest

from tests.factories import make_pair
from trading_desk.config import DeskConfig
from trading_desk.execution.paper import PaperExecutor
from trading_desk.models import Chain, Order, Side
from trading_desk.portfolio import Portfolio


@pytest.fixture
def executor():
    return PaperExecutor(DeskConfig())


def buy(executor, portfolio, pair, usd, stop=0.0007):
    order = Order(
        chain=pair.chain,
        token_address=pair.base_address,
        symbol=pair.base_symbol,
        side=Side.BUY,
        usd_amount=usd,
        reference_price=pair.price_usd,
        pair=pair,
    )
    return portfolio.apply_buy(executor.execute(order, pair), pair, stop_price=stop)


def sell(executor, portfolio, pair, quantity, reason="take-profit"):
    order = Order(
        chain=pair.chain,
        token_address=pair.base_address,
        symbol=pair.base_symbol,
        side=Side.SELL,
        quantity=quantity,
        reference_price=pair.price_usd,
        pair=pair,
    )
    return portfolio.apply_sell(executor.execute(order, pair), reason=reason)


def test_buy_moves_cash_into_a_position(executor, pair):
    portfolio = Portfolio(100.0)
    position = buy(executor, portfolio, pair, 20.0)

    assert portfolio.cash_usd == pytest.approx(100 - 20 - 0.03, abs=0.01)  # gas on top
    assert position.quantity > 0
    assert portfolio.holds(Chain.SOLANA, "TOKEN1")
    assert portfolio.equity_usd < 100  # costs are real


def test_partial_exit_releases_cost_basis_proportionally(executor, pair):
    portfolio = Portfolio(100.0)
    position = buy(executor, portfolio, pair, 20.0)
    original_basis = position.cost_basis_usd

    sell(executor, portfolio, pair, position.quantity * 0.4)

    assert position.quantity == pytest.approx(position.initial_quantity * 0.6)
    assert position.cost_basis_usd == pytest.approx(original_basis * 0.6, rel=1e-6)


def test_unrealized_pnl_is_not_double_counted_after_a_scale_out(executor, pair):
    """The remainder must carry only its own share of the original cost."""
    portfolio = Portfolio(100.0)
    position = buy(executor, portfolio, pair, 20.0)
    pair.price_usd = 0.002
    position.last_price = 0.002

    sell(executor, portfolio, pair, position.quantity * 0.5)

    # The remainder marks at the price our own exit pushed the pool to, which
    # is below the pre-trade quote — that impact is real and already paid.
    assert position.last_price < 0.002
    expected_value = position.quantity * position.last_price
    assert position.market_value_usd == pytest.approx(expected_value, rel=1e-9)
    assert position.unrealized_usd == pytest.approx(expected_value - position.cost_basis_usd)
    assert position.realized_usd > 0


def test_full_exit_closes_the_line(executor, pair):
    portfolio = Portfolio(100.0)
    position = buy(executor, portfolio, pair, 20.0)
    trade = sell(executor, portfolio, pair, position.quantity, reason="stop-loss")

    assert not portfolio.holds(Chain.SOLANA, "TOKEN1")
    assert trade.reason == "stop-loss"
    assert len(portfolio.closed_trades) == 1


def test_a_flat_round_trip_loses_exactly_the_costs(executor, pair):
    portfolio = Portfolio(100.0)
    position = buy(executor, portfolio, pair, 20.0)
    sell(executor, portfolio, pair, position.quantity)

    assert portfolio.equity_usd < 100.0
    assert portfolio.cash_usd == pytest.approx(portfolio.equity_usd)
    assert portfolio.fees_paid_usd > 0


def test_adding_to_a_position_averages_the_entry(executor, pair):
    portfolio = Portfolio(200.0)
    buy(executor, portfolio, pair, 20.0)
    pair.price_usd = 0.002
    position = buy(executor, portfolio, pair, 20.0)

    assert 0.001 < position.avg_entry_price < 0.002
    assert position.initial_quantity == pytest.approx(position.quantity)


def test_stats_report_win_rate_and_profit_factor(executor, pair):
    portfolio = Portfolio(200.0)
    position = buy(executor, portfolio, pair, 20.0)
    pair.price_usd = 0.003
    sell(executor, portfolio, pair, position.quantity)

    other = make_pair(base_address="TOKEN2", base_symbol="CAT", price_usd=0.01)
    position = buy(executor, portfolio, other, 20.0)
    other.price_usd = 0.005
    sell(executor, portfolio, other, position.quantity)

    stats = portfolio.stats()
    assert stats["trades"] == 2
    assert stats["wins"] == 1 and stats["losses"] == 1
    assert stats["win_rate"] == pytest.approx(0.5)
    assert stats["profit_factor"] > 0


def test_selling_something_not_held_is_a_no_op(executor, pair):
    portfolio = Portfolio(100.0)
    assert sell(executor, portfolio, pair, 100.0) is None
    assert portfolio.cash_usd == 100.0
