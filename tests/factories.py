"""Builders for market-data objects used across the trading desk tests.

Everything here builds objects that look like live market data without any
network: these tests must be runnable in a sandbox with no route to
DexScreener, Blockscout or any RPC.
"""
import time

from trading_desk.models import Chain, Pair, TxnCounts


def make_pair(**overrides) -> Pair:
    """A healthy, mildly trending Solana pair — the baseline every test bends."""
    defaults = dict(
        chain=Chain.SOLANA,
        pair_address="POOL1",
        base_address="TOKEN1",
        base_symbol="DOGE",
        base_name="Dogecoin Killer",
        quote_symbol="SOL",
        dex_id="raydium",
        price_usd=0.001,
        liquidity_usd=120_000.0,
        fdv_usd=900_000.0,
        volume_5m=3_000.0,
        volume_1h=24_000.0,
        volume_24h=300_000.0,
        change_5m=0.04,
        change_1h=0.35,
        change_24h=1.2,
        txns_5m=TxnCounts(buys=40, sells=15),
        txns_1h=TxnCounts(buys=300, sells=220),
        txns_24h=TxnCounts(buys=2000, sells=1800),
        created_at=time.time() - 4 * 3600,
    )
    defaults.update(overrides)
    return Pair(**defaults)


def make_hot_pair(**overrides) -> Pair:
    """A pair strong enough to clear the entry threshold."""
    defaults = dict(
        liquidity_usd=250_000.0,
        volume_5m=6_000.0,
        change_5m=0.09,
        change_1h=0.9,
        txns_5m=TxnCounts(buys=70, sells=18),
        txns_1h=TxnCounts(buys=420, sells=230),
        created_at=time.time() - 3 * 3600,
    )
    defaults.update(overrides)
    return make_pair(**defaults)


class FakeFeed:
    """A one-chain feed serving canned pairs, with optional failure injection."""

    def __init__(self, chain=Chain.SOLANA, pairs=None, fail=False):
        self.chain = chain
        self.pairs = list(pairs or [])
        self.fail = fail
        self.discover_calls = 0

    def discover(self, limit=30):
        self.discover_calls += 1
        if self.fail:
            raise RuntimeError("feed is down")
        return list(self.pairs)[:limit]

    def get_pair(self, token_address):
        if self.fail:
            raise RuntimeError("feed is down")
        for pair in self.pairs:
            if pair.base_address.lower() == token_address.lower():
                return pair
        return None

    def set_price(self, token_address, price, liquidity=None):
        for pair in self.pairs:
            if pair.base_address.lower() == token_address.lower():
                pair.price_usd = price
                if liquidity is not None:
                    pair.liquidity_usd = liquidity
