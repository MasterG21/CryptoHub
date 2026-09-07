"""The interface every chain feed implements, plus the multi-chain fan-out."""
from __future__ import annotations

from typing import Iterable, Optional, Protocol, runtime_checkable

from ..models import Chain, Pair


class FeedError(RuntimeError):
    """Raised when a feed cannot answer a question it is required to answer."""


@runtime_checkable
class MarketDataFeed(Protocol):
    """A source of tradeable pairs for exactly one chain."""

    chain: Chain

    def discover(self, limit: int = 30) -> list[Pair]:
        """Candidate pairs worth screening right now, best-effort."""

    def get_pair(self, token_address: str) -> Optional[Pair]:
        """Current state of one token's primary pool, or None if unknown."""


class MultiChainFeed:
    """Fans discovery and quote lookups out across per-chain feeds.

    One chain being down must not stop the desk trading the others, so every
    call is wrapped: failures are collected into ``errors`` for the caller to
    report and the remaining chains still return data.
    """

    def __init__(self, feeds: Iterable[MarketDataFeed]):
        self.feeds: dict[Chain, MarketDataFeed] = {f.chain: f for f in feeds}
        self.errors: list[tuple[Chain, str]] = []

    def reset_errors(self) -> None:
        self.errors = []

    def discover(self, limit_per_chain: int = 30) -> list[Pair]:
        self.reset_errors()
        pairs: list[Pair] = []
        for chain, feed in self.feeds.items():
            try:
                pairs.extend(feed.discover(limit=limit_per_chain))
            except Exception as exc:  # noqa: BLE001 - one chain must not sink the rest
                self.errors.append((chain, str(exc)))
        return pairs

    def get_pair(self, chain: Chain, token_address: str) -> Optional[Pair]:
        feed = self.feeds.get(chain)
        if feed is None:
            return None
        try:
            return feed.get_pair(token_address)
        except Exception as exc:  # noqa: BLE001
            self.errors.append((chain, str(exc)))
            return None
