"""The trap gate: what the desk is allowed to trade at all.

This runs before any momentum scoring, and it is deliberately the harshest
layer in the system. Its job is not to find winners; it is to make the set of
losses survivable by refusing tokens whose structure means you may not be able
to sell at all.

Two rules shape everything here:

**Unknown is not OK.** A missing liquidity number is not zero and not fine — it
is a fact the desk could not establish, and the desk does not put money behind
facts it could not establish. Every unknown that matters is a rejection with a
message that says so.

**Rejections are structural, warnings are qualitative.** A rejection means a
verifiable property makes the token untradeable (no depth, no sells, no price).
A warning means the token is tradeable but worse, and costs score.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from .config import SafetyConfig
from .marketdata.history import PriceHistory
from .models import Chain, Pair, SafetyVerdict

# A deep screen returns a 0-100 health score for a token, or None if it could
# not be run. robinhood_meme_scan.screen.analyze_token is the implementation
# behind the default one; the indirection keeps this module network-free and
# unit-testable.
DeepScreen = Callable[[Pair], Optional[int]]


@dataclass
class _Check:
    """One deduction applied to the safety score."""

    label: str
    points: int


class SafetyGate:
    def __init__(
        self,
        config: SafetyConfig,
        deep_screen: Optional[DeepScreen] = None,
        history: Optional[PriceHistory] = None,
    ):
        self.config = config
        self.deep_screen = deep_screen
        self.history = history

    def evaluate(self, pair: Pair) -> SafetyVerdict:
        cfg = self.config
        rejections: list[str] = []
        warnings: list[str] = []
        skipped: list[str] = []
        deductions = 0

        # --- Can we price it at all? -----------------------------------------
        if not pair.price_usd or pair.price_usd <= 0:
            rejections.append("no USD price available")
        if pair.liquidity_usd is None:
            rejections.append("pool liquidity unknown")
        elif pair.liquidity_usd < cfg.min_liquidity_usd:
            rejections.append(
                f"liquidity ${pair.liquidity_usd:,.0f} below floor ${cfg.min_liquidity_usd:,.0f}"
            )
        elif cfg.max_liquidity_usd and pair.liquidity_usd > cfg.max_liquidity_usd:
            rejections.append(f"liquidity ${pair.liquidity_usd:,.0f} above ceiling")

        # --- Age --------------------------------------------------------------
        age = pair.age_minutes
        if age is None:
            skipped.append("pair age unknown")
            deductions += 5
        else:
            if age < cfg.min_age_minutes:
                rejections.append(
                    f"pool is {age:.0f}m old, under the {cfg.min_age_minutes:.0f}m minimum"
                )
            elif cfg.max_age_minutes and age > cfg.max_age_minutes:
                rejections.append(f"pool is {age / 1440:.1f} days old, past the window")

        # --- Float vs pool depth ---------------------------------------------
        ratio = pair.liquidity_to_fdv
        if ratio is None:
            skipped.append("FDV unknown, cannot check float backing")
            deductions += 5
        elif ratio < cfg.min_liquidity_to_fdv:
            rejections.append(
                f"only {ratio * 100:.2f}% of FDV sits in the pool "
                f"(minimum {cfg.min_liquidity_to_fdv * 100:.1f}%)"
            )
        elif ratio < cfg.min_liquidity_to_fdv * 2:
            warnings.append(f"thin float backing: {ratio * 100:.2f}% of FDV in pool")
            deductions += 10

        # --- Real trading, or theatre? ---------------------------------------
        self._check_activity(pair, rejections, warnings, skipped)
        deductions += self._check_wash_trading(pair, warnings)
        deductions += self._check_sell_starvation(pair, rejections)

        # --- Chain-specific deep screen --------------------------------------
        if pair.chain is Chain.ROBINHOOD and cfg.require_robinhood_screen:
            deductions += self._run_deep_screen(pair, rejections, skipped)
        elif self.deep_screen is not None:
            deductions += self._run_deep_screen(pair, rejections, skipped)

        score = max(0, min(100, 100 - deductions - 25 * len(rejections)))
        return SafetyVerdict(
            passed=not rejections,
            score=score,
            rejections=rejections,
            warnings=warnings,
            checks_skipped=skipped,
        )

    def _check_activity(
        self,
        pair: Pair,
        rejections: list[str],
        warnings: list[str],
        skipped: list[str],
    ) -> None:
        """Require evidence that other people are actually trading this token.

        Preferred evidence is transaction counts and volume. Chains without an
        indexer publish neither, so the desk's own observed price series is
        accepted as a fallback: a price that has moved across a real window is
        proof that trades happened, even when nothing reports the count.
        """
        cfg = self.config
        has_txn_data = pair.txns_1h.total > 0 or pair.txns_24h.total > 0
        has_volume_data = pair.volume_1h is not None or pair.volume_24h is not None

        if has_txn_data and pair.txns_1h.total < cfg.min_txns_1h:
            rejections.append(
                f"only {pair.txns_1h.total} trades in the last hour "
                f"(minimum {cfg.min_txns_1h})"
            )
        if has_volume_data:
            volume = pair.volume_1h
            if volume is not None and volume < cfg.min_volume_1h_usd:
                rejections.append(
                    f"1h volume ${volume:,.0f} below the ${cfg.min_volume_1h_usd:,.0f} minimum"
                )
        if has_txn_data or has_volume_data:
            return

        # No indexer coverage: fall back to observed price action.
        skipped.append("no transaction/volume data from this chain's feed")
        observed = self.history.change_over(pair.key, 60) if self.history else None
        if observed is None:
            rejections.append(
                "no trade data and not enough observed price history to substitute"
            )
        elif abs(observed) < 1e-6:
            rejections.append("price has not moved over the observed window; pool looks dead")
        else:
            warnings.append("activity inferred from observed price only, not trade counts")

    def _check_wash_trading(self, pair: Pair, warnings: list[str]) -> int:
        """Volume far beyond what the pool's depth can support is manufactured.

        Turning over 40x the pool in an hour is not organic interest; it is
        usually a bot cycling the same inventory to paint the volume charts
        that discovery tools rank on.
        """
        cfg = self.config
        if not pair.liquidity_usd or pair.volume_1h is None:
            return 0
        turnover = pair.volume_1h / pair.liquidity_usd
        if turnover > cfg.max_volume_to_liquidity:
            warnings.append(f"1h volume is {turnover:.0f}x pool depth; likely wash trading")
            return 20
        if turnover > cfg.max_volume_to_liquidity / 2:
            warnings.append(f"elevated turnover: {turnover:.0f}x pool depth in 1h")
            return 8
        return 0

    def _check_sell_starvation(self, pair: Pair, rejections: list[str]) -> int:
        """Buys with almost no sells is the honeypot signature.

        On a normal pool sells run at roughly 40-60% of trades. A pool with a
        hundred buys and two sells usually means sells are reverting — the
        tax, blacklist or transfer hook only bites on the way out.
        """
        cfg = self.config
        for window, counts in (("1h", pair.txns_1h), ("24h", pair.txns_24h)):
            ratio = counts.buy_ratio
            if ratio is None or counts.total < 20:
                continue
            if ratio >= cfg.max_sell_starvation_ratio:
                rejections.append(
                    f"{ratio * 100:.0f}% of {window} trades are buys with almost no sells "
                    "— classic honeypot pattern"
                )
                return 0
            if ratio >= cfg.max_sell_starvation_ratio - 0.07:
                return 10
        return 0

    def _run_deep_screen(self, pair: Pair, rejections: list[str], skipped: list[str]) -> int:
        if self.deep_screen is None:
            skipped.append("contract-level screen not configured for this chain")
            return 10
        try:
            score = self.deep_screen(pair)
        except Exception as exc:  # noqa: BLE001 - a screener outage is not a verdict
            skipped.append(f"contract screen failed: {exc}")
            return 10
        if score is None:
            skipped.append("contract screen returned no score")
            return 10
        minimum = self.config.min_robinhood_health_score
        if score < minimum:
            rejections.append(f"contract health score {score}/100 below the {minimum} minimum")
            return 0
        # Above the bar, but the margin still costs something.
        return max(0, (minimum + 20 - score) // 2)


def make_robinhood_deep_screen(explorer, options) -> DeepScreen:
    """Wire the existing robinhood_meme_scan contract screen into the gate.

    Kept out of ``SafetyGate`` so the gate has no network dependency and can be
    tested with a stub; the desk builds this once and passes it in.
    """
    from robinhood_meme_scan.screen import analyze_token

    def screen(pair: Pair) -> Optional[int]:
        report = analyze_token(explorer, pair.base_address, options)
        return report.score

    return screen
