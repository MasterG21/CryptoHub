"""The trap gate must reject on facts, and must reject on missing facts too."""
import time

import pytest

from tests.factories import make_pair
from trading_desk.config import SafetyConfig
from trading_desk.marketdata.history import PriceHistory
from trading_desk.models import Chain, TxnCounts
from trading_desk.safety import SafetyGate


@pytest.fixture
def gate():
    return SafetyGate(SafetyConfig())


def test_healthy_pair_passes_cleanly(gate, pair):
    verdict = gate.evaluate(pair)
    assert verdict.passed
    assert verdict.score == 100
    assert verdict.rejections == []


def test_thin_liquidity_is_rejected(gate):
    verdict = gate.evaluate(make_pair(liquidity_usd=4_000))
    assert not verdict.passed
    assert "below floor" in verdict.rejections[0]


def test_unknown_liquidity_is_rejected_not_assumed_zero(gate):
    """Unknown must not silently read as either safe or as no liquidity."""
    verdict = gate.evaluate(make_pair(liquidity_usd=None))
    assert not verdict.passed
    assert any("unknown" in r for r in verdict.rejections)


def test_missing_price_is_rejected(gate):
    verdict = gate.evaluate(make_pair(price_usd=None))
    assert not verdict.passed
    assert any("price" in r for r in verdict.rejections)


def test_brand_new_pool_is_rejected(gate):
    verdict = gate.evaluate(make_pair(created_at=time.time() - 120))
    assert not verdict.passed
    assert any("old" in r for r in verdict.rejections)


def test_stale_pool_is_rejected(gate):
    verdict = gate.evaluate(make_pair(created_at=time.time() - 40 * 86400))
    assert not verdict.passed
    assert any("days old" in r for r in verdict.rejections)


def test_honeypot_sell_starvation_is_rejected(gate):
    """A hundred buys and two sells means sells are reverting."""
    verdict = gate.evaluate(
        make_pair(txns_1h=TxnCounts(buys=200, sells=2), txns_24h=TxnCounts(buys=400, sells=5))
    )
    assert not verdict.passed
    assert any("honeypot" in r for r in verdict.rejections)


def test_wash_trading_warns_and_costs_score(gate):
    verdict = gate.evaluate(make_pair(liquidity_usd=20_000, volume_1h=2_000_000))
    assert verdict.passed  # tradeable, but flagged and penalised
    assert any("wash trading" in w for w in verdict.warnings)
    assert verdict.score < 100


def test_thin_float_against_fdv_is_rejected(gate):
    verdict = gate.evaluate(make_pair(liquidity_usd=20_000, fdv_usd=50_000_000))
    assert not verdict.passed
    assert any("FDV" in r for r in verdict.rejections)


def test_dead_pool_with_few_trades_is_rejected(gate):
    verdict = gate.evaluate(make_pair(txns_1h=TxnCounts(buys=3, sells=2), volume_1h=200))
    assert not verdict.passed


def test_chain_without_txn_data_falls_back_to_observed_history():
    """Robinhood Chain has no indexer; observed price movement substitutes."""
    history = PriceHistory()
    gate = SafetyGate(SafetyConfig(), history=history)
    pair = make_pair(
        chain=Chain.ROBINHOOD,
        txns_5m=TxnCounts(),
        txns_1h=TxnCounts(),
        txns_24h=TxnCounts(),
        volume_1h=None,
        volume_24h=None,
    )
    now = time.time()
    history.observe(pair.key, 0.0008, 120_000, timestamp=now - 3700)
    history.observe(pair.key, 0.001, 120_000, timestamp=now)

    verdict = gate.evaluate(pair)
    assert verdict.passed
    assert any("observed price" in w for w in verdict.warnings)
    assert any("no transaction/volume data" in s for s in verdict.checks_skipped)


def test_chain_without_txn_data_or_history_is_rejected():
    gate = SafetyGate(SafetyConfig(), history=PriceHistory())
    pair = make_pair(
        chain=Chain.ROBINHOOD,
        txns_5m=TxnCounts(),
        txns_1h=TxnCounts(),
        txns_24h=TxnCounts(),
        volume_1h=None,
        volume_24h=None,
    )
    verdict = gate.evaluate(pair)
    assert not verdict.passed
    assert any("not enough observed price history" in r for r in verdict.rejections)


def test_robinhood_deep_screen_gates_on_contract_health():
    pair = make_pair(chain=Chain.ROBINHOOD)
    passing = SafetyGate(SafetyConfig(), deep_screen=lambda p: 85)
    failing = SafetyGate(SafetyConfig(), deep_screen=lambda p: 30)

    assert passing.evaluate(pair).passed
    verdict = failing.evaluate(pair)
    assert not verdict.passed
    assert any("health score" in r for r in verdict.rejections)


def test_deep_screen_failure_is_not_treated_as_a_pass():
    def broken(pair):
        raise RuntimeError("explorer down")

    gate = SafetyGate(SafetyConfig(), deep_screen=broken)
    verdict = gate.evaluate(make_pair(chain=Chain.ROBINHOOD))
    assert any("contract screen failed" in s for s in verdict.checks_skipped)
    assert verdict.score < 100
