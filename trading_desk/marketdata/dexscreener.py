"""DexScreener feed — covers Solana and BNB Chain from one public API.

DexScreener indexes the DEXes on both chains and reports depth, volume and
buy/sell counts per window, which is exactly the input the momentum and safety
layers need. It is unauthenticated and rate-limited, so this client batches
token lookups (the API takes up to 30 comma-separated addresses) and keeps a
short response cache.

Units, normalised on the way in so nothing downstream has to remember:
  * ``priceChange`` arrives in percent   -> stored as a fraction (5.2 -> 0.052)
  * ``pairCreatedAt`` arrives in millis  -> stored as unix seconds
Anything missing stays None rather than becoming 0.
"""
from __future__ import annotations

import time
from typing import Any, Iterable, Optional

import requests

from ..models import Chain, Pair, TxnCounts
from .base import FeedError

DEFAULT_BASE_URL = "https://api.dexscreener.com"

# DexScreener's chainId strings for the chains this desk trades.
_CHAIN_IDS = {Chain.SOLANA: "solana", Chain.BNB: "bsc"}

# Seed queries for discovery: the quote assets that essentially every memecoin
# pool on these chains is paired against.
_DISCOVERY_QUERIES = {
    Chain.SOLANA: ("SOL", "USDC"),
    Chain.BNB: ("WBNB", "USDT"),
}

_MAX_ADDRESSES_PER_CALL = 30


def _f(value: Any) -> Optional[float]:
    """Float or None. DexScreener sends prices as strings and omits empties."""
    if value is None or value == "":
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if out != out else out  # drop NaN


def _pct(value: Any) -> Optional[float]:
    raw = _f(value)
    return None if raw is None else raw / 100.0


def _txns(block: Any) -> TxnCounts:
    if not isinstance(block, dict):
        return TxnCounts()
    try:
        return TxnCounts(buys=int(block.get("buys") or 0), sells=int(block.get("sells") or 0))
    except (TypeError, ValueError):
        return TxnCounts()


def parse_pair(raw: dict, chain: Optional[Chain] = None) -> Optional[Pair]:
    """Turn one DexScreener pair object into a ``Pair``.

    Returns None for anything unusable — an unknown chain, or a pair with no
    base token address — instead of raising, so one malformed entry in a
    30-item response doesn't discard the other 29.
    """
    if not isinstance(raw, dict):
        return None
    chain_id = raw.get("chainId")
    resolved = chain
    if resolved is None:
        for candidate, cid in _CHAIN_IDS.items():
            if cid == chain_id:
                resolved = candidate
                break
    if resolved is None:
        return None

    base = raw.get("baseToken") or {}
    base_address = base.get("address")
    if not base_address:
        return None

    volume = raw.get("volume") or {}
    change = raw.get("priceChange") or {}
    txns = raw.get("txns") or {}
    liquidity = raw.get("liquidity") or {}

    created_ms = _f(raw.get("pairCreatedAt"))
    return Pair(
        chain=resolved,
        pair_address=raw.get("pairAddress") or "",
        base_address=base_address,
        base_symbol=base.get("symbol") or "?",
        base_name=base.get("name"),
        quote_symbol=(raw.get("quoteToken") or {}).get("symbol"),
        dex_id=raw.get("dexId"),
        price_usd=_f(raw.get("priceUsd")),
        liquidity_usd=_f(liquidity.get("usd")),
        fdv_usd=_f(raw.get("fdv")),
        market_cap_usd=_f(raw.get("marketCap")),
        volume_5m=_f(volume.get("m5")),
        volume_1h=_f(volume.get("h1")),
        volume_6h=_f(volume.get("h6")),
        volume_24h=_f(volume.get("h24")),
        change_5m=_pct(change.get("m5")),
        change_1h=_pct(change.get("h1")),
        change_6h=_pct(change.get("h6")),
        change_24h=_pct(change.get("h24")),
        txns_5m=_txns(txns.get("m5")),
        txns_1h=_txns(txns.get("h1")),
        txns_24h=_txns(txns.get("h24")),
        created_at=created_ms / 1000.0 if created_ms else None,
    )


def best_pool_per_token(pairs: Iterable[Pair]) -> list[Pair]:
    """Collapse a token's pools down to its deepest one.

    A token often has several pools across DEXes. The desk trades one line per
    token, and the deepest pool is both the one that prices it and the one it
    can actually get filled in.
    """
    best: dict[str, Pair] = {}
    for pair in pairs:
        current = best.get(pair.key)
        if current is None or (pair.liquidity_usd or 0) > (current.liquidity_usd or 0):
            best[pair.key] = pair
    return list(best.values())


class DexScreenerFeed:
    """Read-only market data for one chain, via the public DexScreener API."""

    def __init__(
        self,
        chain: Chain,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 15.0,
        cache_seconds: float = 20.0,
        session: Optional[requests.Session] = None,
    ):
        if chain not in _CHAIN_IDS:
            raise ValueError(f"DexScreener feed does not cover {chain.label}")
        self.chain = chain
        self.chain_id = _CHAIN_IDS[chain]
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.cache_seconds = cache_seconds
        self.session = session or requests.Session()
        self._cache: dict[str, tuple[float, Any]] = {}

    def _get(self, path: str, params: Optional[dict] = None) -> Any:
        cache_key = f"{path}?{sorted((params or {}).items())}"
        hit = self._cache.get(cache_key)
        now = time.time()
        if hit and now - hit[0] < self.cache_seconds:
            return hit[1]
        try:
            resp = self.session.get(
                f"{self.base_url}{path}", params=params, timeout=self.timeout
            )
        except requests.RequestException as exc:
            raise FeedError(f"DexScreener request failed: {exc}") from exc
        if resp.status_code == 429:
            raise FeedError("DexScreener rate limit hit; back off and retry")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        payload = resp.json()
        self._cache[cache_key] = (now, payload)
        return payload

    def _pairs_from(self, payload: Any) -> list[Pair]:
        if not payload:
            return []
        raw_pairs = payload.get("pairs") if isinstance(payload, dict) else payload
        if not isinstance(raw_pairs, list):
            return []
        out = []
        for item in raw_pairs:
            pair = parse_pair(item)
            if pair is not None and pair.chain is self.chain:
                out.append(pair)
        return out

    def search(self, query: str) -> list[Pair]:
        return self._pairs_from(self._get("/latest/dex/search", {"q": query}))

    def get_tokens(self, addresses: Iterable[str]) -> list[Pair]:
        """Pools for up to 30 token addresses per request."""
        addresses = [a for a in addresses if a]
        found: list[Pair] = []
        for i in range(0, len(addresses), _MAX_ADDRESSES_PER_CALL):
            batch = addresses[i : i + _MAX_ADDRESSES_PER_CALL]
            found.extend(self._pairs_from(self._get(f"/latest/dex/tokens/{','.join(batch)}")))
        return found

    def latest_profiles(self) -> list[str]:
        """Token addresses from DexScreener's newly-profiled list, this chain only.

        This is the closest thing the free API has to a new-listings firehose.
        It is not exhaustive — it only shows tokens whose teams paid for or
        claimed a profile — so discovery treats it as one input, not the input.
        """
        payload = self._get("/token-profiles/latest/v1")
        if not isinstance(payload, list):
            return []
        return [
            item.get("tokenAddress")
            for item in payload
            if isinstance(item, dict)
            and item.get("chainId") == self.chain_id
            and item.get("tokenAddress")
        ]

    def discover(self, limit: int = 30) -> list[Pair]:
        """Assemble a candidate set from profiles plus quote-asset searches.

        An error from one source is tolerated on purpose — a 429 on the
        profiles endpoint should still leave the search results usable. But if
        *every* source fails and nothing came back, that is raised rather than
        returned as an empty list: "no tokens look good right now" and "this
        machine cannot reach DexScreener" are very different situations, and a
        desk that reports them identically will sit there scanning nothing and
        looking healthy.
        """
        pairs: list[Pair] = []
        failures: list[str] = []

        try:
            addresses = self.latest_profiles()
            if addresses:
                pairs.extend(self.get_tokens(addresses[: _MAX_ADDRESSES_PER_CALL * 2]))
        except (FeedError, requests.RequestException) as exc:
            failures.append(f"token profiles: {exc}")

        for query in _DISCOVERY_QUERIES.get(self.chain, ()):
            try:
                pairs.extend(self.search(query))
            except (FeedError, requests.RequestException) as exc:
                failures.append(f"search {query!r}: {exc}")

        if not pairs and failures:
            raise FeedError(
                f"every {self.chain.label} discovery source failed: " + "; ".join(failures)
            )

        deduped = best_pool_per_token(pairs)
        deduped.sort(key=lambda p: p.volume_1h or 0.0, reverse=True)
        return deduped[:limit]

    def get_pair(self, token_address: str) -> Optional[Pair]:
        pools = best_pool_per_token(self.get_tokens([token_address]))
        return pools[0] if pools else None
