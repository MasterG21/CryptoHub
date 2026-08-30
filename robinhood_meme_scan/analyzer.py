"""Heuristic health scoring for a Robinhood Chain meme coin.

This is a transparent point-deduction heuristic, not a formal audit. It
flags patterns that correlate with rug pulls and low-quality launches; it
cannot prove a token is safe, and a high score is not investment advice.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .blockscout import BURN_ADDRESSES, Holder, TokenInfo

STARTING_SCORE = 100

MINT_KEYWORDS = ("function mint", "_mint(")
DANGEROUS_KEYWORDS = (
    "function blacklist",
    "function pause",
    "function setfee",
    "function excludefromfee",
    "onlyowner",
)


@dataclass
class Flag:
    label: str
    points: int  # negative = deduction
    detail: str


@dataclass
class HealthReport:
    token: TokenInfo
    flags: list[Flag] = field(default_factory=list)
    holder_top1_pct: Optional[float] = None
    holder_top10_pct: Optional[float] = None
    liquidity_checked: bool = False
    liquidity_found: bool = False
    ownership_renounced: Optional[bool] = None
    contract_age_note: Optional[str] = None
    deployer: Optional[str] = None
    deployer_token_count: Optional[int] = None

    @property
    def score(self) -> int:
        return max(0, min(100, STARTING_SCORE + sum(f.points for f in self.flags)))

    @property
    def verdict(self) -> str:
        s = self.score
        if s >= 80:
            return "Looks healthy"
        if s >= 50:
            return "Caution"
        return "High risk"


def _add(report: HealthReport, label: str, points: int, detail: str) -> None:
    report.flags.append(Flag(label=label, points=points, detail=detail))


def score_holders(report: HealthReport, holders: list[Holder], total_supply: int, lp_address: Optional[str]) -> None:
    if total_supply <= 0 or not holders:
        _add(report, "holder-data", -5, "Holder balances unavailable; skipping concentration check")
        return

    excluded = set(BURN_ADDRESSES)
    if lp_address:
        excluded.add(lp_address.lower())

    relevant = [h for h in holders if h.address.lower() not in excluded]
    if not relevant:
        return

    top1 = relevant[0].balance / total_supply * 100
    top10 = sum(h.balance for h in relevant[:10]) / total_supply * 100
    report.holder_top1_pct = top1
    report.holder_top10_pct = top10

    if top1 > 20:
        _add(report, "holder-concentration", -20, f"Top wallet holds {top1:.1f}% of supply (excl. LP/burn)")
    elif top1 > 10:
        _add(report, "holder-concentration", -10, f"Top wallet holds {top1:.1f}% of supply (excl. LP/burn)")

    if top10 > 70:
        _add(report, "holder-concentration-top10", -15, f"Top 10 wallets hold {top10:.1f}% of supply (excl. LP/burn)")
    elif top10 > 50:
        _add(report, "holder-concentration-top10", -8, f"Top 10 wallets hold {top10:.1f}% of supply (excl. LP/burn)")


def score_holder_count(report: HealthReport, holder_count: Optional[int]) -> None:
    if holder_count is None:
        return
    if holder_count < 25:
        _add(report, "low-holder-count", -10, f"Only {holder_count} holders on record")


def score_verification(report: HealthReport, contract: Optional[dict]) -> None:
    if not contract:
        _add(report, "unverified-contract", -30, "Contract source is not verified on Blockscout")
        return

    source = (contract.get("source_code") or "").lower()
    if not source:
        _add(report, "unverified-contract", -30, "Contract source is not verified on Blockscout")
        return

    if any(k in source for k in MINT_KEYWORDS):
        _add(report, "mint-function", -15, "Verified source contains a mint function outside typical fixed-supply patterns")

    hits = [k for k in DANGEROUS_KEYWORDS if k in source]
    if hits:
        _add(
            report,
            "sensitive-functions",
            -10,
            f"Verified source references privileged functions: {', '.join(hits)}",
        )


def score_ownership(report: HealthReport, renounced: Optional[bool]) -> None:
    report.ownership_renounced = renounced
    if renounced is False:
        _add(report, "owner-not-renounced", -10, "Contract owner has not renounced ownership")


def score_liquidity(report: HealthReport, checked: bool, found: bool, token_balance: Optional[int] = None) -> None:
    report.liquidity_checked = checked
    report.liquidity_found = found
    if not checked:
        return
    if not found:
        _add(report, "no-liquidity-pool", -15, "No Uniswap V3 pool found for token/WETH at common fee tiers")
    elif token_balance == 0:
        _add(report, "empty-liquidity-pool", -15, "Pool exists but holds zero balance of this token")


def score_age(report: HealthReport, hours_old: Optional[float]) -> None:
    if hours_old is None:
        return
    if hours_old < 24:
        report.contract_age_note = f"Deployed {hours_old:.1f}h ago"
        _add(report, "very-new-contract", -10, f"Contract is only {hours_old:.1f} hours old")
    else:
        report.contract_age_note = f"Deployed ~{hours_old / 24:.1f} days ago"


def score_deployer(
    report: HealthReport, deployer: Optional[str], deployed_token_count: Optional[int]
) -> None:
    """Flag serial launchers.

    Deploying many tokens is not proof of bad intent — some teams ship
    repeatedly — but a wallet with a long tail of prior launches is the
    pattern behind launch-farming, and it is worth surfacing rather than
    burying. The deduction stays modest for that reason.
    """
    report.deployer = deployer
    report.deployer_token_count = deployed_token_count
    if deployed_token_count is None:
        return
    if deployed_token_count >= 10:
        _add(
            report,
            "serial-deployer",
            -15,
            f"Deployer wallet has launched {deployed_token_count} tokens",
        )
    elif deployed_token_count >= 4:
        _add(
            report,
            "repeat-deployer",
            -8,
            f"Deployer wallet has launched {deployed_token_count} tokens",
        )


def build_report(token: TokenInfo) -> HealthReport:
    return HealthReport(token=token)
