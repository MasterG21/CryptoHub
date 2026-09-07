"""Robinhood Chain feed, built on the explorer and RPC rather than an indexer.

Robinhood Chain is new enough that no aggregator publishes rolling volume or
price-change windows for it, so this feed differs from the DexScreener one in
two ways that matter:

  * Price comes from the Uniswap V3 pool's slot0, converted to USD with a
    reference price for the chain's native asset. Without a V3 factory address,
    a WETH address and that reference price, prices are unknown and the safety
    gate will refuse to trade the chain rather than guess.
  * Momentum windows are filled from the desk's own observations
    (``PriceHistory``). A token here is not tradeable until the desk has
    watched it long enough to measure a real change.

Volume and buy/sell counts stay None: they cannot be derived from spot reads,
and inventing them would let a token clear thresholds it never met.
"""
from __future__ import annotations

from typing import Callable, Optional, Union

from robinhood_meme_scan.blockscout import BlockscoutClient
from robinhood_meme_scan.onchain import find_liquidity_pool, get_web3, read_pool_state

from ..models import Chain, Pair
from .base import FeedError
from .history import PriceHistory

NativePrice = Union[float, Callable[[], Optional[float]], None]


class RobinhoodFeed:
    """Market data for Robinhood Chain ERC-20 pools."""

    chain = Chain.ROBINHOOD

    def __init__(
        self,
        rpc_url: str,
        explorer_api: str,
        v3_factory: Optional[str] = None,
        weth: Optional[str] = None,
        native_usd_price: NativePrice = None,
        history: Optional[PriceHistory] = None,
        explorer: Optional[BlockscoutClient] = None,
        web3=None,
    ):
        self.rpc_url = rpc_url
        self.v3_factory = v3_factory
        self.weth = weth
        self.native_usd_price = native_usd_price
        self.history = history if history is not None else PriceHistory()
        self.explorer = explorer or BlockscoutClient(base_url=explorer_api)
        self._web3 = web3

    @property
    def priced(self) -> bool:
        """Whether this feed can produce USD prices at all."""
        return bool(self.v3_factory and self.weth and self._native_usd() is not None)

    def _native_usd(self) -> Optional[float]:
        source = self.native_usd_price
        if callable(source):
            try:
                source = source()
            except Exception:
                return None
        try:
            value = float(source) if source is not None else None
        except (TypeError, ValueError):
            return None
        return value if value and value > 0 else None

    def _w3(self):
        if self._web3 is None:
            self._web3 = get_web3(self.rpc_url)
        return self._web3

    def list_tokens(self, limit: int = 30) -> list[dict]:
        """Recent ERC-20s from the explorer's token index."""
        try:
            data = self.explorer._get("/tokens", params={"type": "ERC-20"})
        except Exception as exc:  # noqa: BLE001
            raise FeedError(f"explorer token listing failed: {exc}") from exc
        if not data:
            return []
        items = data.get("items", data if isinstance(data, list) else [])
        return [i for i in items if isinstance(i, dict)][:limit]

    def _build_pair(self, token_address: str, meta: Optional[dict] = None) -> Optional[Pair]:
        meta = meta or {}
        symbol = meta.get("symbol") or "?"
        name = meta.get("name")
        try:
            decimals = int(meta.get("decimals") or 18)
        except (TypeError, ValueError):
            decimals = 18

        pair = Pair(
            chain=self.chain,
            pair_address="",
            base_address=token_address,
            base_symbol=symbol,
            base_name=name,
            quote_symbol="WETH",
            dex_id="uniswap-v3",
        )

        native_usd = self._native_usd()
        if not (self.v3_factory and self.weth and native_usd):
            # No pricing inputs: return the pair with price/liquidity unknown so
            # the safety gate can reject it explicitly instead of silently
            # dropping the whole chain.
            return pair

        pair.native_usd_price = native_usd
        pool = find_liquidity_pool(self._w3(), token_address, self.v3_factory, self.weth)
        if pool is None:
            return pair

        state = read_pool_state(
            self._w3(),
            pool.pool_address,
            token_address,
            self.weth,
            token_decimals=decimals,
            quote_decimals=18,
            fee_tier=pool.fee_tier,
        )
        pair.pair_address = pool.pool_address
        if state.price_in_quote is not None:
            pair.price_usd = state.price_in_quote * native_usd
        token_side_usd = (
            (state.token_balance / 10**decimals) * pair.price_usd
            if pair.price_usd is not None
            else 0.0
        )
        quote_side_usd = (state.quote_balance / 10**18) * native_usd
        if state.quote_balance or state.token_balance:
            pair.liquidity_usd = token_side_usd + quote_side_usd

        total_supply = meta.get("total_supply")
        if pair.price_usd is not None and total_supply is not None:
            try:
                pair.fdv_usd = (int(total_supply) / 10**decimals) * pair.price_usd
            except (TypeError, ValueError):
                pair.fdv_usd = None

        return pair

    def _apply_history(self, pair: Pair) -> Pair:
        """Record this observation and backfill the momentum windows from it."""
        if pair.price_usd:
            self.history.observe(pair.key, pair.price_usd, pair.liquidity_usd)
        pair.change_5m = self.history.change_over(pair.key, 5)
        pair.change_1h = self.history.change_over(pair.key, 60)
        pair.change_6h = self.history.change_over(pair.key, 360)
        return pair

    def discover(self, limit: int = 30) -> list[Pair]:
        pairs: list[Pair] = []
        for item in self.list_tokens(limit=limit):
            address = item.get("address") or item.get("address_hash")
            if isinstance(address, dict):
                address = address.get("hash")
            if not address:
                continue
            try:
                pair = self._build_pair(address, item)
            except Exception:  # noqa: BLE001 - one bad token must not sink the scan
                continue
            if pair is not None:
                pairs.append(self._apply_history(pair))
        return pairs

    def get_pair(self, token_address: str) -> Optional[Pair]:
        meta: dict = {}
        try:
            token = self.explorer.get_token(token_address)
            meta = {
                "symbol": token.symbol,
                "name": token.name,
                "decimals": token.decimals,
                "total_supply": token.total_supply,
            }
        except Exception:  # noqa: BLE001 - fall back to on-chain-only data
            pass
        pair = self._build_pair(token_address, meta)
        return self._apply_history(pair) if pair else None
