"""Feed parsing and the locally-observed price history."""
import time

import pytest

from trading_desk.marketdata.base import MultiChainFeed
from trading_desk.marketdata.dexscreener import (
    DexScreenerFeed,
    best_pool_per_token,
    parse_pair,
)
from trading_desk.marketdata.history import PriceHistory
from trading_desk.models import Chain

RAW_PAIR = {
    "chainId": "solana",
    "dexId": "raydium",
    "pairAddress": "POOL1",
    "baseToken": {"address": "TOKEN1", "name": "Dogecoin Killer", "symbol": "DOGE"},
    "quoteToken": {"symbol": "SOL"},
    "priceUsd": "0.001234",
    "liquidity": {"usd": 84000.5},
    "fdv": 1_200_000,
    "marketCap": 900_000,
    "volume": {"m5": 900, "h1": 12000, "h6": 60000, "h24": 200000},
    "priceChange": {"m5": 4.5, "h1": 22.0, "h6": -3.0, "h24": 140.0},
    "txns": {"m5": {"buys": 30, "sells": 10}, "h1": {"buys": 300, "sells": 250}},
    "pairCreatedAt": 1_700_000_000_000,
}


def test_percentages_become_fractions():
    """DexScreener sends 22.0 for +22%; everything downstream expects 0.22."""
    pair = parse_pair(RAW_PAIR)
    assert pair.change_1h == pytest.approx(0.22)
    assert pair.change_24h == pytest.approx(1.40)


def test_millisecond_timestamps_become_seconds():
    pair = parse_pair(RAW_PAIR)
    assert pair.created_at == pytest.approx(1_700_000_000.0)


def test_string_prices_are_parsed():
    assert parse_pair(RAW_PAIR).price_usd == pytest.approx(0.001234)


def test_missing_fields_stay_none_rather_than_zero():
    """A pool with no 24h history has an unknown 24h change, not a flat one."""
    raw = {**RAW_PAIR, "volume": {"m5": 900}, "priceChange": {"m5": 4.5}, "liquidity": {}}
    pair = parse_pair(raw)
    assert pair.volume_24h is None
    assert pair.change_1h is None
    assert pair.liquidity_usd is None


def test_unusable_entries_are_dropped_not_raised():
    assert parse_pair({"chainId": "solana", "baseToken": {}}) is None
    assert parse_pair({"chainId": "ethereum", "baseToken": {"address": "X"}}) is None
    assert parse_pair("not a dict") is None


def test_derived_metrics():
    pair = parse_pair(RAW_PAIR)
    assert pair.liquidity_to_fdv == pytest.approx(84000.5 / 1_200_000)
    assert pair.txns_5m.buy_ratio == pytest.approx(0.75)
    assert pair.key == "solana:token1"


def test_the_deepest_pool_wins_when_a_token_has_several():
    shallow = parse_pair({**RAW_PAIR, "pairAddress": "P2", "liquidity": {"usd": 10}})
    deep = parse_pair(RAW_PAIR)
    best = best_pool_per_token([shallow, deep])
    assert len(best) == 1
    assert best[0].pair_address == "POOL1"


def test_feed_rejects_a_chain_it_does_not_cover():
    with pytest.raises(ValueError, match="does not cover"):
        DexScreenerFeed(Chain.ROBINHOOD)


class _Response:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.text = str(payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(f"HTTP {self.status_code}")


class _Session:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def get(self, url, params=None, timeout=None, headers=None):
        self.calls += 1
        return _Response(self.payload)


def test_responses_are_cached_within_the_ttl():
    session = _Session({"pairs": [RAW_PAIR]})
    feed = DexScreenerFeed(Chain.SOLANA, session=session, cache_seconds=60)

    feed.search("SOL")
    feed.search("SOL")
    assert session.calls == 1


def test_get_pair_returns_the_deepest_pool():
    session = _Session({"pairs": [RAW_PAIR, {**RAW_PAIR, "pairAddress": "P2", "liquidity": {"usd": 5}}]})
    feed = DexScreenerFeed(Chain.SOLANA, session=session)
    assert feed.get_pair("TOKEN1").pair_address == "POOL1"


def test_multichain_feed_isolates_a_failing_chain():
    class Broken:
        chain = Chain.BNB

        def discover(self, limit=30):
            raise RuntimeError("down")

        def get_pair(self, address):
            raise RuntimeError("down")

    class Working:
        chain = Chain.SOLANA

        def discover(self, limit=30):
            return [parse_pair(RAW_PAIR)]

        def get_pair(self, address):
            return parse_pair(RAW_PAIR)

    feed = MultiChainFeed([Working(), Broken()])
    pairs = feed.discover()

    assert len(pairs) == 1
    assert feed.errors and feed.errors[0][0] is Chain.BNB


# ------------------------------------------------------------------- history


def test_change_over_a_covered_window():
    history = PriceHistory()
    now = time.time()
    history.observe("k", 1.0, timestamp=now - 3600)
    history.observe("k", 1.5, timestamp=now)
    assert history.change_over("k", 60) == pytest.approx(0.5)


def test_change_is_unknown_without_enough_coverage():
    """Two ticks a minute apart cannot answer 'what did the last hour do'."""
    history = PriceHistory()
    now = time.time()
    history.observe("k", 1.0, timestamp=now - 60)
    history.observe("k", 1.5, timestamp=now)
    assert history.change_over("k", 60) is None
    assert history.change_over("k", 1) == pytest.approx(0.5)


def test_out_of_order_observations_keep_the_series_sorted():
    history = PriceHistory()
    now = time.time()
    history.observe("k", 1.0, timestamp=now - 3600)
    history.observe("k", 2.0, timestamp=now)
    history.observe("k", 1.5, timestamp=now - 1800)  # a retried fetch arriving late
    assert history.latest("k").price == pytest.approx(2.0)
    assert history.change_over("k", 60) == pytest.approx(1.0)


def test_liquidity_change_is_tracked():
    history = PriceHistory()
    now = time.time()
    history.observe("k", 1.0, liquidity_usd=100_000, timestamp=now - 600)
    history.observe("k", 1.0, liquidity_usd=50_000, timestamp=now)
    assert history.liquidity_change("k", 10) == pytest.approx(-0.5)


def test_old_observations_are_pruned():
    history = PriceHistory(max_age_seconds=60)
    history.observe("k", 1.0, timestamp=time.time() - 3600)
    history.observe("k", 2.0)
    assert history.coverage_minutes("k") < 1


def test_non_positive_prices_are_ignored():
    history = PriceHistory()
    history.observe("k", 0.0)
    history.observe("k", -1.0)
    assert history.latest("k") is None


class _FailingSession:
    def get(self, url, params=None, timeout=None, headers=None):
        raise __import__("requests").RequestException("no route to host")


def test_discovery_raises_when_every_source_fails():
    """'Nothing looks good' and 'the network is down' must not look identical."""
    from trading_desk.marketdata.base import FeedError

    feed = DexScreenerFeed(Chain.SOLANA, session=_FailingSession())
    with pytest.raises(FeedError, match="every Solana discovery source failed"):
        feed.discover()


def test_discovery_tolerates_one_failing_source():
    class PartialSession:
        def __init__(self):
            self.calls = 0

        def get(self, url, params=None, timeout=None, headers=None):
            self.calls += 1
            if "token-profiles" in url:
                raise __import__("requests").RequestException("429")
            return _Response({"pairs": [RAW_PAIR]})

    feed = DexScreenerFeed(Chain.SOLANA, session=PartialSession(), cache_seconds=0)
    assert len(feed.discover()) == 1
