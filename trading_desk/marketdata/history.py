"""Locally observed price history.

Some chains have no indexer that will hand you a 1h price change. Rather than
skip momentum on those chains, the desk records what it sees on every poll and
derives the windows itself. A token is only tradeable once its own observed
history is long enough to measure — see ``has_coverage``.

This is also why the desk needs to run a while before it trades a new chain:
it is building the history that the strategy reads.
"""
from __future__ import annotations

import bisect
import time
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Observation:
    timestamp: float
    price: float
    liquidity_usd: Optional[float] = None


class PriceHistory:
    """Per-token time series, capped in memory and pruned by age.

    Observations are appended in time order by the desk loop. ``_series`` keeps
    them sorted so window lookups can binary-search rather than scan.
    """

    def __init__(self, max_age_seconds: float = 6 * 3600, max_points: int = 720):
        self.max_age_seconds = max_age_seconds
        self.max_points = max_points
        self._series: dict[str, list[Observation]] = {}

    def observe(
        self,
        key: str,
        price: float,
        liquidity_usd: Optional[float] = None,
        timestamp: Optional[float] = None,
    ) -> None:
        if price <= 0:
            return
        ts = time.time() if timestamp is None else timestamp
        series = self._series.setdefault(key, [])
        obs = Observation(timestamp=ts, price=price, liquidity_usd=liquidity_usd)
        if series and ts < series[-1].timestamp:
            # Out-of-order arrival (a retried fetch, a clock nudge): insert in
            # place so the series stays sorted for the bisect lookups below.
            idx = bisect.bisect_left([o.timestamp for o in series], ts)
            series.insert(idx, obs)
        else:
            series.append(obs)
        self._prune(key)

    def _prune(self, key: str) -> None:
        series = self._series[key]
        cutoff = time.time() - self.max_age_seconds
        first_fresh = bisect.bisect_left([o.timestamp for o in series], cutoff)
        if first_fresh:
            del series[:first_fresh]
        if len(series) > self.max_points:
            del series[: len(series) - self.max_points]
        if not series:
            self._series.pop(key, None)

    def latest(self, key: str) -> Optional[Observation]:
        series = self._series.get(key)
        return series[-1] if series else None

    def coverage_minutes(self, key: str) -> float:
        """How much wall-clock history this token actually has."""
        series = self._series.get(key)
        if not series or len(series) < 2:
            return 0.0
        return (series[-1].timestamp - series[0].timestamp) / 60.0

    def has_coverage(self, key: str, minutes: float) -> bool:
        return self.coverage_minutes(key) >= minutes

    def _observation_at(self, key: str, target_ts: float) -> Optional[Observation]:
        """The last observation at or before ``target_ts``."""
        series = self._series.get(key)
        if not series:
            return None
        idx = bisect.bisect_right([o.timestamp for o in series], target_ts) - 1
        if idx < 0:
            return None
        return series[idx]

    def change_over(self, key: str, minutes: float) -> Optional[float]:
        """Fractional price change over the window, or None without coverage.

        Returns None rather than 0.0 when the history is too short: a token the
        desk has watched for 40 seconds has an *unknown* 1h change, and letting
        that read as "flat" would quietly feed the strategy a fabricated number.
        """
        series = self._series.get(key)
        if not series or len(series) < 2:
            return None
        now = series[-1].timestamp
        if (now - series[0].timestamp) / 60.0 < minutes * 0.8:
            return None
        past = self._observation_at(key, now - minutes * 60.0)
        if past is None or past.price <= 0 or past is series[-1]:
            return None
        return series[-1].price / past.price - 1.0

    def liquidity_change(self, key: str, minutes: float) -> Optional[float]:
        series = self._series.get(key)
        if not series or len(series) < 2:
            return None
        past = self._observation_at(key, series[-1].timestamp - minutes * 60.0)
        current = series[-1].liquidity_usd
        if past is None or not past.liquidity_usd or current is None:
            return None
        return current / past.liquidity_usd - 1.0

    def tracked_keys(self) -> list[str]:
        return list(self._series)

    def __len__(self) -> int:
        return len(self._series)
