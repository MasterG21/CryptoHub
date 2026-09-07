"""Core value types shared by every layer of the desk.

Everything here is plain data: the market-data layer produces ``Pair``s, the
safety and strategy layers turn those into ``Candidate``s, risk turns a
candidate into an ``Order``, and execution turns an order into a ``Fill``.
Keeping them dataclasses (rather than dicts) means a missing field is an
AttributeError at the seam that produced it, not a silent None deep in sizing.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Chain(str, Enum):
    SOLANA = "solana"
    BNB = "bsc"
    ROBINHOOD = "robinhood"

    @property
    def label(self) -> str:
        return {"solana": "Solana", "bsc": "BNB Chain", "robinhood": "Robinhood Chain"}[
            self.value
        ]

    @property
    def native_symbol(self) -> str:
        return {"solana": "SOL", "bsc": "BNB", "robinhood": "ETH"}[self.value]


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class ExitReason(str, Enum):
    STOP_LOSS = "stop-loss"
    TRAILING_STOP = "trailing-stop"
    TAKE_PROFIT = "take-profit"
    TIME_STOP = "time-stop"
    LIQUIDITY_DRAIN = "liquidity-drain"
    MOMENTUM_DEAD = "momentum-dead"
    KILL_SWITCH = "kill-switch"
    MANUAL = "manual"


@dataclass
class TxnCounts:
    """Buy/sell transaction counts over one window."""

    buys: int = 0
    sells: int = 0

    @property
    def total(self) -> int:
        return self.buys + self.sells

    @property
    def buy_ratio(self) -> Optional[float]:
        """Share of trades that were buys, or None when the window is empty."""
        if self.total == 0:
            return None
        return self.buys / self.total


@dataclass
class Pair:
    """A tradeable token/quote pool, normalised across data sources.

    Every numeric field is Optional because no upstream source populates all of
    them for every pool, and a memecoin pool minutes old legitimately has no
    24h history. Downstream code must treat None as "unknown" and never as 0 —
    a token with unknown liquidity is not a token with no liquidity.
    """

    chain: Chain
    pair_address: str
    base_address: str
    base_symbol: str
    base_name: Optional[str] = None
    quote_symbol: Optional[str] = None
    dex_id: Optional[str] = None
    price_usd: Optional[float] = None
    liquidity_usd: Optional[float] = None
    fdv_usd: Optional[float] = None
    market_cap_usd: Optional[float] = None
    volume_5m: Optional[float] = None
    volume_1h: Optional[float] = None
    volume_6h: Optional[float] = None
    volume_24h: Optional[float] = None
    change_5m: Optional[float] = None
    change_1h: Optional[float] = None
    change_6h: Optional[float] = None
    change_24h: Optional[float] = None
    txns_5m: TxnCounts = field(default_factory=TxnCounts)
    txns_1h: TxnCounts = field(default_factory=TxnCounts)
    txns_24h: TxnCounts = field(default_factory=TxnCounts)
    created_at: Optional[float] = None  # unix seconds
    fetched_at: float = field(default_factory=time.time)
    # USD price of the chain's native asset at fetch time, when the feed knows
    # it. Live order sizing needs it to convert a USD amount into the native
    # units an aggregator quotes in; feeds that price in USD directly leave it
    # None and live sizing refuses rather than guessing.
    native_usd_price: Optional[float] = None

    @property
    def key(self) -> str:
        """Stable identity for a position: one line per token per chain."""
        return f"{self.chain.value}:{self.base_address.lower()}"

    @property
    def age_minutes(self) -> Optional[float]:
        if self.created_at is None:
            return None
        return max(0.0, (self.fetched_at - self.created_at) / 60.0)

    @property
    def liquidity_to_fdv(self) -> Optional[float]:
        """Pool depth as a fraction of fully diluted value.

        A 2% ratio means the entire market cap is backed by a pool you could
        drain with a mid-size order. Low is normal for memecoins; near-zero
        with a large FDV is a token priced off a sliver of real float.
        """
        if self.liquidity_usd is None or not self.fdv_usd:
            return None
        return self.liquidity_usd / self.fdv_usd


@dataclass
class SafetyVerdict:
    """Output of the trap gate: whether a pair may be traded at all."""

    passed: bool
    score: int  # 0-100, higher = fewer structural red flags
    rejections: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checks_skipped: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if self.rejections:
            return self.rejections[0]
        if self.warnings:
            return self.warnings[0]
        return "clean"


@dataclass
class Candidate:
    """A pair that cleared the safety gate, with its momentum score attached."""

    pair: Pair
    safety: SafetyVerdict
    score: float = 0.0
    components: dict[str, float] = field(default_factory=dict)
    rejections: list[str] = field(default_factory=list)

    @property
    def tradeable(self) -> bool:
        return self.safety.passed and not self.rejections


@dataclass
class Order:
    """An intent to trade, before execution decides what actually filled."""

    chain: Chain
    token_address: str
    symbol: str
    side: Side
    usd_amount: Optional[float] = None  # buys are sized in USD
    quantity: Optional[float] = None  # sells are sized in tokens
    reference_price: Optional[float] = None
    pair: Optional[Pair] = None
    reason: str = ""
    max_slippage_pct: float = 0.15


@dataclass
class Fill:
    """What execution actually achieved, including every cost."""

    order: Order
    quantity: float
    price: float  # effective price per token, after slippage
    gross_usd: float  # quantity * reference price
    fee_usd: float
    gas_usd: float
    slippage_pct: float
    timestamp: float = field(default_factory=time.time)
    tx_ref: Optional[str] = None

    @property
    def net_usd(self) -> float:
        """Signed cash impact: negative for buys (money out), positive for sells."""
        notional = self.quantity * self.price
        if self.order.side is Side.BUY:
            return -(notional + self.fee_usd + self.gas_usd)
        return notional - self.fee_usd - self.gas_usd


@dataclass
class Position:
    """An open holding, with the exit levels that were set when it opened."""

    chain: Chain
    token_address: str
    symbol: str
    quantity: float
    avg_entry_price: float
    cost_basis_usd: float  # total cash paid in, fees and gas included
    stop_price: float
    opened_at: float = field(default_factory=time.time)
    high_water_price: float = 0.0
    entry_liquidity_usd: Optional[float] = None
    last_price: Optional[float] = None
    last_liquidity_usd: Optional[float] = None
    realized_usd: float = 0.0
    scale_outs_done: int = 0
    trailing_armed: bool = False
    pair_address: Optional[str] = None
    initial_quantity: float = 0.0

    def __post_init__(self) -> None:
        if self.high_water_price <= 0:
            self.high_water_price = self.avg_entry_price
        if self.last_price is None:
            self.last_price = self.avg_entry_price
        if self.initial_quantity <= 0:
            # Scale-out ladders are sized against the position as first opened,
            # so selling "40% at 2x" stays 40% of the original after an earlier
            # tranche has already gone out.
            self.initial_quantity = self.quantity

    @property
    def key(self) -> str:
        return f"{self.chain.value}:{self.token_address.lower()}"

    @property
    def market_value_usd(self) -> float:
        return self.quantity * (self.last_price or self.avg_entry_price)

    @property
    def unrealized_usd(self) -> float:
        """Open P&L on the remaining size only.

        cost_basis_usd is reduced proportionally as size is scaled out, so
        this stays correct after partial exits; booked profit lives in
        realized_usd and is deliberately not double-counted here.
        """
        return self.market_value_usd - self.cost_basis_usd

    @property
    def total_pnl_usd(self) -> float:
        return self.unrealized_usd + self.realized_usd

    @property
    def multiple(self) -> float:
        """Current price as a multiple of average entry (2.0 = a 2x)."""
        if self.avg_entry_price <= 0:
            return 1.0
        return (self.last_price or self.avg_entry_price) / self.avg_entry_price

    @property
    def age_minutes(self) -> float:
        return (time.time() - self.opened_at) / 60.0

    @property
    def risk_per_token(self) -> float:
        """Distance from entry to the initial stop — one 'R' of risk."""
        return max(0.0, self.avg_entry_price - self.stop_price)
