"""Desk configuration: every tunable, one place, with defaults sized for $100.

Defaults here are deliberately conservative for a small account. Two of them
are load-bearing and should not be raised casually:

``max_pool_impact_pct`` — on a memecoin you are not a price taker. Buying 5% of
a pool moves the price against you roughly 5% on the way in and again on the
way out. This cap, not the position cap, is what usually binds on a thin pool.

``risk_per_trade_pct`` — with a stop this wide, fixed-fractional sizing is the
only thing standing between a losing streak and a zeroed account.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Optional

from .models import Chain


@dataclass
class RiskConfig:
    # 2% is already past the growth-optimal fraction for the desk's default
    # assumed trade distribution (see trading_desk/growth.py, and the warning
    # `run` prints at startup). It is set here anyway because the alternative
    # is worse: growth-optimal for that distribution is ~0.3%, which on a $100
    # account is a $1 position — below the minimum that gas makes worth
    # placing. A small account cannot bet small enough, and pretending
    # otherwise with a prettier default would hide that. Run `plan` before
    # trusting this number, and lower it as the account grows.
    risk_per_trade_pct: float = 0.02  # fraction of equity risked to the stop
    max_position_pct: float = 0.25  # cap on any single position vs equity
    max_pool_impact_pct: float = 0.01  # cap on order size vs pool liquidity
    max_concurrent_positions: int = 4
    max_positions_per_chain: int = 2
    min_position_usd: float = 5.0  # below this, gas eats the trade
    cash_reserve_pct: float = 0.10  # never deploy the last slice of the account
    daily_loss_limit_pct: float = 0.25  # halt new entries after this drawdown
    max_consecutive_losses: int = 6
    equity_floor_usd: float = 15.0  # stop trading rather than dust out


@dataclass
class StrategyConfig:
    stop_loss_pct: float = 0.30  # hard stop below entry
    # Once a trade has run this far, its stop moves up to the entry price plus
    # costs, so a winner can no longer become a loser. Without this there is no
    # protection at all below trail_arm_multiple: a position could rally 55%,
    # reverse, and still stop out at a full loss.
    #
    # The level is a genuine trade-off and not a solved one. Too low and normal
    # memecoin volatility shakes you out of the runners that pay for everything;
    # too high and the gap this closes reopens. 1.35 leaves a 26% retrace of
    # room, which is wide for most assets and only average for these. Tune it
    # against your own trades once you have a hundred of them.
    breakeven_arm_multiple: float = 1.35
    breakeven_buffer_pct: float = 0.012  # clear the round trip, not just entry
    trail_arm_multiple: float = 1.6  # arm the trailing stop at +60%
    trail_giveback_pct: float = 0.25  # then trail this far under the high
    scale_out_levels: tuple[float, ...] = (2.0, 4.0, 10.0)
    scale_out_fractions: tuple[float, ...] = (0.4, 0.3, 0.2)
    time_stop_minutes: float = 180.0
    time_stop_min_multiple: float = 1.15  # must be up this much by then
    liquidity_drain_pct: float = 0.40  # exit if the pool sheds this much depth
    momentum_dead_change_1h: float = -0.25
    # After closing a token, refuse to re-enter it for this long. Without it a
    # stop-out and a re-entry land in the same tick: the token's momentum
    # fields still look strong the instant after it drops through the stop, so
    # the desk buys back exactly what just hurt it, and pays the round trip
    # twice for the privilege.
    reentry_cooldown_minutes: float = 120.0
    min_entry_score: float = 0.55  # composite momentum score needed to open
    max_change_5m: float = 1.00  # don't chase a candle already up 100% in 5m
    min_change_1h: float = 0.02  # require the hour to be pointing up


@dataclass
class SafetyConfig:
    min_liquidity_usd: float = 15_000.0
    max_liquidity_usd: Optional[float] = None
    min_age_minutes: float = 20.0
    max_age_minutes: Optional[float] = 20_160.0  # ~14 days; older isn't a "new" trade
    min_txns_1h: int = 30
    min_volume_1h_usd: float = 5_000.0
    max_volume_to_liquidity: float = 40.0  # wash-trading tell
    min_liquidity_to_fdv: float = 0.01  # 1% of FDV in the pool, minimum
    max_sell_starvation_ratio: float = 0.97  # ~all buys, no sells = honeypot tell
    min_robinhood_health_score: int = 60  # from robinhood_meme_scan's screen
    require_robinhood_screen: bool = True


@dataclass
class ExecutionConfig:
    mode: str = "paper"  # "paper" | "live"
    dex_fee_pct: float = 0.0030
    gas_usd: dict[str, float] = field(
        default_factory=lambda: {
            Chain.SOLANA.value: 0.03,
            Chain.BNB.value: 0.35,
            Chain.ROBINHOOD.value: 0.05,
        }
    )
    max_slippage_pct: float = 0.15
    # Gas is paid in the chain's native coin, never in the token being traded,
    # and it is what an *exit* costs too. A wallet that runs dry cannot sell —
    # stops stop firing and the position rides to zero with no way out. These
    # floors are in native units (SOL, BNB) and are deliberately generous:
    # roughly ten exits' worth, so a bad day cannot strand the book.
    min_native_reserve: dict[str, float] = field(
        default_factory=lambda: {
            Chain.SOLANA.value: 0.02,   # ~10 swaps plus token-account rent
            Chain.BNB.value: 0.005,     # ~10 swaps at typical BNB gas
            Chain.ROBINHOOD.value: 0.002,
        }
    )
    # Live trading is refused unless this is explicitly true AND a signer is
    # supplied. Two independent switches, because one typo should not be able
    # to turn a simulation into real orders.
    allow_live_trading: bool = False


@dataclass
class DeskConfig:
    starting_capital_usd: float = 100.0
    target_usd: float = 1_000_000.0
    chains: tuple[Chain, ...] = (Chain.SOLANA, Chain.BNB, Chain.ROBINHOOD)
    poll_interval_seconds: float = 60.0
    max_candidates_per_chain: int = 30
    journal_path: str = "desk_journal.sqlite3"
    risk: RiskConfig = field(default_factory=RiskConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)

    def gas_for(self, chain: Chain) -> float:
        return self.execution.gas_usd.get(chain.value, 0.10)

    def native_reserve_for(self, chain: Chain) -> float:
        """Native coin that must stay in the wallet to fund exits."""
        return self.execution.min_native_reserve.get(chain.value, 0.0)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["chains"] = [c.value for c in self.chains]
        data["strategy"]["scale_out_levels"] = list(self.strategy.scale_out_levels)
        data["strategy"]["scale_out_fractions"] = list(self.strategy.scale_out_fractions)
        return data


_SECTIONS = {
    "risk": RiskConfig,
    "strategy": StrategyConfig,
    "safety": SafetyConfig,
    "execution": ExecutionConfig,
}


def _coerce_section(section_cls, raw: dict) -> Any:
    """Build a config section, ignoring unknown keys but reporting them.

    Silently dropping a misspelled key in a risk config is how an account ends
    up trading with defaults the operator thought they had overridden, so the
    caller gets the unknown names back to surface.
    """
    known = {f.name for f in fields(section_cls)}
    accepted = {k: v for k, v in raw.items() if k in known}
    unknown = sorted(set(raw) - known)
    section = section_cls(**accepted)
    for key in ("scale_out_levels", "scale_out_fractions"):
        if key in accepted and isinstance(getattr(section, key), list):
            setattr(section, key, tuple(getattr(section, key)))
    return section, unknown


def load_config(path: Optional[str] = None) -> tuple[DeskConfig, list[str]]:
    """Load config from a JSON file, then let environment variables override.

    Returns the config plus a list of warnings (unknown keys, bad env values)
    so the CLI can print them rather than failing on a typo.
    """
    warnings: list[str] = []
    raw: dict[str, Any] = {}
    if path:
        with open(path) as fh:
            raw = json.load(fh)

    kwargs: dict[str, Any] = {}
    for name, cls in _SECTIONS.items():
        if isinstance(raw.get(name), dict):
            section, unknown = _coerce_section(cls, raw[name])
            kwargs[name] = section
            warnings += [f"unknown {name} option ignored: {k}" for k in unknown]

    top_level = {f.name for f in fields(DeskConfig)} - set(_SECTIONS)
    for key, value in raw.items():
        if key in _SECTIONS:
            continue
        if key not in top_level:
            warnings.append(f"unknown option ignored: {key}")
            continue
        if key == "chains":
            try:
                kwargs["chains"] = tuple(Chain(c) for c in value)
            except ValueError as exc:
                warnings.append(f"bad chain in config: {exc}")
        else:
            kwargs[key] = value

    cfg = DeskConfig(**kwargs)
    _apply_env_overrides(cfg, warnings)
    return cfg, warnings


_ENV_OVERRIDES: tuple[tuple[str, Optional[str], str, type], ...] = (
    ("DESK_STARTING_CAPITAL", None, "starting_capital_usd", float),
    ("DESK_TARGET_USD", None, "target_usd", float),
    ("DESK_POLL_INTERVAL", None, "poll_interval_seconds", float),
    ("DESK_JOURNAL", None, "journal_path", str),
    ("DESK_RISK_PER_TRADE", "risk", "risk_per_trade_pct", float),
    ("DESK_MAX_POSITIONS", "risk", "max_concurrent_positions", int),
    ("DESK_DAILY_LOSS_LIMIT", "risk", "daily_loss_limit_pct", float),
    ("DESK_MIN_LIQUIDITY", "safety", "min_liquidity_usd", float),
    ("DESK_STOP_LOSS", "strategy", "stop_loss_pct", float),
    ("DESK_MODE", "execution", "mode", str),
)


def _apply_env_overrides(cfg: DeskConfig, warnings: list[str]) -> None:
    for env_name, section, attr, caster in _ENV_OVERRIDES:
        raw = os.environ.get(env_name)
        if raw is None:
            continue
        try:
            value = caster(raw)
        except ValueError:
            warnings.append(f"{env_name}={raw!r} is not a valid {caster.__name__}; ignored")
            continue
        target = getattr(cfg, section) if section else cfg
        setattr(target, attr, value)

    chains = os.environ.get("DESK_CHAINS")
    if chains:
        try:
            cfg.chains = tuple(Chain(c.strip()) for c in chains.split(",") if c.strip())
        except ValueError as exc:
            warnings.append(f"DESK_CHAINS ignored: {exc}")


def validate_config(cfg: DeskConfig) -> list[str]:
    """Return human-readable problems that would make the desk misbehave.

    These are errors of arithmetic, not taste — a stop above the entry, or
    scale-out fractions summing past 100% of the position.
    """
    problems: list[str] = []
    r, s = cfg.risk, cfg.strategy

    if not 0 < r.risk_per_trade_pct < 1:
        problems.append("risk.risk_per_trade_pct must be between 0 and 1")
    if not 0 < r.max_position_pct <= 1:
        problems.append("risk.max_position_pct must be between 0 and 1")
    if not 0 < r.max_pool_impact_pct <= 1:
        problems.append("risk.max_pool_impact_pct must be between 0 and 1")
    if not 0 <= r.cash_reserve_pct < 1:
        problems.append("risk.cash_reserve_pct must be between 0 and 1")
    if r.max_concurrent_positions < 1:
        problems.append("risk.max_concurrent_positions must be at least 1")
    if not 0 < s.stop_loss_pct < 1:
        problems.append("strategy.stop_loss_pct must be between 0 and 1")
    if not 0 < s.trail_giveback_pct < 1:
        problems.append("strategy.trail_giveback_pct must be between 0 and 1")
    if s.trail_arm_multiple <= 1:
        problems.append("strategy.trail_arm_multiple must be greater than 1")
    if len(s.scale_out_levels) != len(s.scale_out_fractions):
        problems.append("strategy.scale_out_levels and scale_out_fractions must be the same length")
    elif sum(s.scale_out_fractions) > 1.0 + 1e-9:
        problems.append("strategy.scale_out_fractions sum to more than the whole position")
    elif list(s.scale_out_levels) != sorted(s.scale_out_levels):
        problems.append("strategy.scale_out_levels must be in ascending order")
    if cfg.execution.mode not in ("paper", "live"):
        problems.append("execution.mode must be 'paper' or 'live'")
    if cfg.starting_capital_usd <= 0:
        problems.append("starting_capital_usd must be positive")
    if cfg.target_usd <= cfg.starting_capital_usd:
        problems.append("target_usd must exceed starting_capital_usd")
    if not cfg.chains:
        problems.append("at least one chain must be enabled")
    return problems
