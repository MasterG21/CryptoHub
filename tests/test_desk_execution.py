"""Fill economics, slippage limits, and the guard on live trading."""
import pytest

from tests.factories import make_pair
from trading_desk.config import DeskConfig
from trading_desk.execution.base import (
    ExecutionError,
    SlippageExceeded,
    buy_impact_pct,
    round_trip_cost_pct,
    sell_impact_pct,
)
from trading_desk.execution.live import LiveExecutor, LiveTradingUnavailable
from trading_desk.execution.paper import PaperExecutor
from trading_desk.models import Chain, Order, Side


@pytest.fixture
def cfg():
    return DeskConfig()


def order(side=Side.BUY, **overrides):
    defaults = dict(
        chain=Chain.SOLANA,
        token_address="TOKEN1",
        symbol="DOGE",
        side=side,
        reference_price=0.001,
        max_slippage_pct=0.15,
    )
    defaults.update(overrides)
    return Order(**defaults)


# --------------------------------------------------------------- cost model


def test_impact_scales_with_order_size_against_pool_depth():
    assert buy_impact_pct(100, 100_000) == pytest.approx(0.002)
    assert buy_impact_pct(1_000, 100_000) == pytest.approx(0.02)


def test_selling_costs_slightly_less_than_buying_the_same_notional():
    """Constant-product maths is asymmetric; the model must reflect that."""
    assert sell_impact_pct(1_000, 100_000) < buy_impact_pct(1_000, 100_000)


def test_unknown_depth_is_treated_as_unlimited_impact_not_none():
    assert buy_impact_pct(100, None) == 1.0
    assert sell_impact_pct(100, 0) == 1.0


def test_round_trip_cost_includes_both_legs_and_fees():
    cost = round_trip_cost_pct(1_000, 100_000, 0.003)
    assert cost == pytest.approx(0.02 + sell_impact_pct(1_000, 100_000) + 0.006)


# ------------------------------------------------------------ paper execution


def test_buy_pays_impact_fees_and_gas(cfg, pair):
    executor = PaperExecutor(cfg)
    fill = executor.execute(order(usd_amount=20.0, pair=pair), pair)

    assert fill.price > 0.001  # bought above the quote
    assert fill.fee_usd == pytest.approx(20.0 * cfg.execution.dex_fee_pct)
    assert fill.gas_usd == cfg.gas_for(Chain.SOLANA)
    assert fill.net_usd == pytest.approx(-(20.0 + fill.gas_usd))


def test_sell_fills_below_the_quote(cfg, pair):
    executor = PaperExecutor(cfg)
    fill = executor.execute(order(Side.SELL, quantity=10_000.0, pair=pair), pair)

    assert fill.price < 0.001
    assert fill.net_usd > 0


def test_order_too_large_for_the_pool_is_refused(cfg):
    executor = PaperExecutor(cfg)
    thin = make_pair(liquidity_usd=5_000)
    with pytest.raises(SlippageExceeded) as exc:
        executor.execute(order(usd_amount=2_000.0, pair=thin), thin)
    assert exc.value.required_pct > 0.15


def test_unknown_liquidity_refuses_to_simulate(cfg):
    executor = PaperExecutor(cfg)
    unpriced = make_pair(liquidity_usd=None)
    with pytest.raises(ExecutionError, match="liquidity unknown"):
        executor.execute(order(usd_amount=20.0, pair=unpriced), unpriced)


def test_missing_reference_price_is_refused(cfg):
    executor = PaperExecutor(cfg)
    unpriced = make_pair(price_usd=None)
    with pytest.raises(ExecutionError, match="reference price"):
        executor.execute(order(usd_amount=20.0, reference_price=None, pair=unpriced), unpriced)


def test_failure_rate_simulates_transactions_that_do_not_land(cfg, pair):
    import random

    executor = PaperExecutor(cfg, failure_rate=1.0, rng=random.Random(1))
    with pytest.raises(ExecutionError, match="front-run"):
        executor.execute(order(usd_amount=20.0, pair=pair), pair)


def test_a_round_trip_on_a_thin_pool_costs_meaningfully_more(cfg):
    """Same $50 order, two pools: the thin one keeps a much bigger cut."""
    executor = PaperExecutor(cfg)
    outcomes = []
    for liquidity in (500_000, 25_000):
        pool = make_pair(liquidity_usd=liquidity)
        bought = executor.execute(order(usd_amount=50.0, pair=pool), pool)
        sold = executor.execute(
            order(Side.SELL, quantity=bought.quantity, pair=pool), pool
        )
        outcomes.append(sold.net_usd + bought.net_usd)
    assert outcomes[0] > outcomes[1]


# -------------------------------------------------------------- live guarding


def test_live_executor_refuses_without_being_armed(cfg, pair):
    with pytest.raises(LiveTradingUnavailable) as exc:
        LiveExecutor(cfg).execute(order(usd_amount=20.0, pair=pair), pair)
    assert "not armed" in str(exc.value)


def test_live_preflight_lists_every_blocker(cfg):
    assert len(LiveExecutor(cfg).preflight()) == 3


def test_both_switches_and_a_signer_are_needed(cfg):
    cfg.execution.mode = "live"
    assert LiveExecutor(cfg).preflight() == [
        "execution.allow_live_trading is false",
        "no TransactionSigner supplied (see execution/live.py)",
    ]

    cfg.execution.allow_live_trading = True
    assert LiveExecutor(cfg).preflight() == [
        "no TransactionSigner supplied (see execution/live.py)"
    ]

    class Signer:
        def sign_and_send(self, chain, payload):
            return "0xdeadbeef"

        def wallet_address(self, chain):
            return "0xwallet"

    assert LiveExecutor(cfg, signer=Signer()).preflight() == []


def test_live_refuses_chains_without_a_configured_router(cfg, pair):
    cfg.execution.mode = "live"
    cfg.execution.allow_live_trading = True

    class Signer:
        def sign_and_send(self, chain, payload):
            raise AssertionError("must not be reached")

        def wallet_address(self, chain):
            return "0xwallet"

    robinhood = make_pair(chain=Chain.ROBINHOOD)
    with pytest.raises(ExecutionError, match="no aggregator route"):
        LiveExecutor(cfg, signer=Signer()).execute(
            order(chain=Chain.ROBINHOOD, usd_amount=20.0, pair=robinhood), robinhood
        )
