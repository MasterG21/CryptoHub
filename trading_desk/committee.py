"""Ten specialists, each with one job and a veto.

Why a committee rather than one function: an entry decision is really a dozen
independent questions, and when a trade goes wrong the useful thing to know is
*which* question was answered badly. A single ``should_i_buy()`` returning True
tells you nothing afterwards. Ten named verdicts with reasons tell you exactly
where the process failed, and let you fix that one thing.

These are deterministic specialists, not language-model calls. A model adds
nothing to "is pool depth above the floor" — it would be slower, cost money per
token per tick, and give a different answer on Tuesday. What the structure buys
is the audit trail and the independent vetoes, and those work better when each
agent is a small, testable, reproducible function.

Order matters. Cheap local checks run before anything that costs a network
call, and the two gates that decide whether a position can be *exited* run
last, closest to the moment of commitment:

    PROFESSOR  capacity and mandate      HELSINKI   exposure and cooldown
    TOKYO      discovery and provenance  DENVER     authenticity of volume
    BERLIN     structural safety         NAIROBI    contract brief
    RIO        momentum                  STOCKHOLM  cost of the round trip
    LISBON     freshness recheck         PALERMO    final approval, exit depth

A single VETO blocks the entry. Agents after the veto do not run, and are
reported as such — "blocked at BERLIN" is more useful than ten verdicts where
nine were never really consulted.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Protocol, runtime_checkable

from .config import DeskConfig
from .execution.base import round_trip_cost_pct, sell_impact_pct
from .marketdata.history import PriceHistory
from .models import Candidate, Chain, Pair, SafetyVerdict
from .portfolio import Portfolio
from .risk import RiskManager, SizingResult, size_position
from .safety import SafetyGate
from .strategy import evaluate_entry, initial_stop_price


class Stance(str, Enum):
    PASS = "pass"
    VETO = "veto"
    NOTE = "note"  # passed, but said something worth recording
    SKIPPED = "skipped"  # never consulted; an earlier agent vetoed


@dataclass
class Verdict:
    agent: str
    role: str
    stance: Stance
    reason: str
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def blocking(self) -> bool:
        return self.stance is Stance.VETO


@dataclass
class ReviewContext:
    """Everything the committee is allowed to look at.

    Passed rather than reached for, so each agent's inputs are explicit and a
    test can construct one without standing up a desk.
    """

    pair: Pair
    config: DeskConfig
    portfolio: Portfolio
    risk: RiskManager
    safety_gate: SafetyGate
    history: PriceHistory
    cooling_off: set[str] = field(default_factory=set)
    feed: Any = None
    # Filled in by agents as they go, so later agents can use earlier findings
    # instead of recomputing them.
    safety: Optional[SafetyVerdict] = None
    candidate: Optional[Candidate] = None
    sizing: Optional[SizingResult] = None
    entry_price: Optional[float] = None
    stop_price: Optional[float] = None


@dataclass
class Review:
    """The committee's full record for one candidate."""

    pair: Pair
    verdicts: list[Verdict] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    # What the committee settled on, carried out for the caller. Sizing is
    # advisory: cash moves as earlier entries fill, so the desk re-sizes at the
    # moment it actually places the order.
    score: float = 0.0
    entry_price: Optional[float] = None
    stop_price: Optional[float] = None
    approved_usd: Optional[float] = None

    def verdict_for(self, agent: str) -> Optional[Verdict]:
        return next((v for v in self.verdicts if v.agent == agent), None)

    def consulted_agent(self, agent: str) -> bool:
        verdict = self.verdict_for(agent)
        return verdict is not None and verdict.stance is not Stance.SKIPPED

    @property
    def approved(self) -> bool:
        return bool(self.verdicts) and not any(v.blocking for v in self.verdicts)

    @property
    def blocked_by(self) -> Optional[Verdict]:
        return next((v for v in self.verdicts if v.blocking), None)

    @property
    def consulted(self) -> list[Verdict]:
        return [v for v in self.verdicts if v.stance is not Stance.SKIPPED]

    @property
    def summary(self) -> str:
        blocker = self.blocked_by
        if blocker:
            return f"{blocker.agent}: {blocker.reason}"
        notes = [v for v in self.verdicts if v.stance is Stance.NOTE]
        if notes:
            return f"{notes[0].agent}: {notes[0].reason}"
        return "cleared by all ten"

    def to_dict(self) -> dict:
        return {
            "symbol": self.pair.base_symbol,
            "chain": self.pair.chain.value,
            "address": self.pair.base_address,
            "approved": self.approved,
            "summary": self.summary,
            "blocked_by": self.blocked_by.agent if self.blocked_by else None,
            "score": round(self.score, 3),
            "approved_usd": self.approved_usd,
            "verdicts": [
                {
                    "agent": v.agent,
                    "role": v.role,
                    "stance": v.stance.value,
                    "reason": v.reason,
                    **({"data": v.data} if v.data else {}),
                }
                for v in self.verdicts
            ],
        }


@runtime_checkable
class Agent(Protocol):
    name: str
    role: str

    def review(self, ctx: ReviewContext) -> Verdict:
        ...


class _BaseAgent:
    name = "AGENT"
    role = "unassigned"

    def _pass(self, reason: str, **data) -> Verdict:
        return Verdict(self.name, self.role, Stance.PASS, reason, data)

    def _veto(self, reason: str, **data) -> Verdict:
        return Verdict(self.name, self.role, Stance.VETO, reason, data)

    def _note(self, reason: str, **data) -> Verdict:
        return Verdict(self.name, self.role, Stance.NOTE, reason, data)


# --------------------------------------------------------------------- agents


class Professor(_BaseAgent):
    """Mandate and capacity. Should the desk be opening anything at all?"""

    name = "PROFESSOR"
    role = "router"

    def review(self, ctx: ReviewContext) -> Verdict:
        equity = ctx.portfolio.equity_usd
        halt = ctx.risk.check_halt(equity)
        if halt:
            return self._veto(f"desk halted: {halt}")
        if ctx.pair.chain not in ctx.config.chains:
            return self._veto(f"{ctx.pair.chain.label} is not in the mandate")
        capacity = ctx.risk.capacity(ctx.portfolio.open_positions)
        if capacity <= 0:
            return self._veto("no position slots free")
        return self._pass(f"{capacity} slot(s) open, equity ${equity:,.2f}", capacity=capacity)


class Tokyo(_BaseAgent):
    """Discovery and provenance. Is this a real, quotable pool?"""

    name = "TOKYO"
    role = "scout"

    def review(self, ctx: ReviewContext) -> Verdict:
        pair = ctx.pair
        if not pair.price_usd or pair.price_usd <= 0:
            return self._veto("no USD price from any feed")
        if not pair.pair_address:
            return self._note("no pool address reported; pricing only")
        age = pair.age_minutes
        if age is None:
            return self._note(f"{pair.base_symbol} on {pair.dex_id or 'unknown dex'}, age unknown")
        return self._pass(
            f"{pair.base_symbol} on {pair.dex_id or '?'}, {age / 60:.1f}h old",
            age_hours=round(age / 60, 2),
        )


class Berlin(_BaseAgent):
    """Structural safety. Runs the full trap gate and reports its verdict."""

    name = "BERLIN"
    role = "conditions"

    def review(self, ctx: ReviewContext) -> Verdict:
        verdict = ctx.safety_gate.evaluate(ctx.pair)
        ctx.safety = verdict
        if not verdict.passed:
            return self._veto(verdict.rejections[0], score=verdict.score,
                              rejections=verdict.rejections)
        if verdict.warnings:
            return self._note(verdict.warnings[0], score=verdict.score)
        return self._pass(f"structure clean, {verdict.score}/100", score=verdict.score)


class Denver(_BaseAgent):
    """Authenticity of the activity. Is the volume people, or one bot?"""

    name = "DENVER"
    role = "noise filter"

    # A pool whose entire hourly volume is a handful of trades is one wallet
    # cycling size, whatever the dollar figure says.
    MIN_TRADES_FOR_VOLUME = 15
    MAX_USD_PER_TRADE_RATIO = 0.25  # one trade worth >25% of the hour is a whale, not a crowd

    def review(self, ctx: ReviewContext) -> Verdict:
        pair = ctx.pair
        volume, trades = pair.volume_1h, pair.txns_1h.total
        if volume is None or not trades:
            return self._note("no volume/trade breakdown to audit")

        # Turnover far beyond the pool's depth is inventory being cycled to
        # paint the volume charts that discovery tools rank on. BERLIN notes
        # elevated turnover; refusing the manufactured kind is this desk's job,
        # because a token can otherwise clear structure on fake activity and
        # then be judged purely on the momentum that activity created.
        if pair.liquidity_usd:
            turnover = volume / pair.liquidity_usd
            limit = ctx.config.safety.max_volume_to_liquidity
            if turnover > limit:
                return self._veto(
                    f"1h volume is {turnover:.0f}x pool depth (limit {limit:.0f}x) "
                    "— manufactured",
                    turnover=round(turnover, 1),
                )

        if trades < self.MIN_TRADES_FOR_VOLUME:
            return self._veto(f"${volume:,.0f} of 1h volume across only {trades} trades")
        per_trade = volume / trades
        if per_trade > volume * self.MAX_USD_PER_TRADE_RATIO:
            return self._veto(f"average trade ${per_trade:,.0f} dominates the hour")
        ratio = pair.txns_1h.buy_ratio
        if ratio is not None and ratio > 0.85:
            return self._note(f"{ratio * 100:.0f}% buys — one-sided, watch the exit")
        return self._pass(f"{trades} trades, ${per_trade:,.0f} average", trades=trades)


class Nairobi(_BaseAgent):
    """Contract brief. What can the token's own code do to a holder?"""

    name = "NAIROBI"
    role = "briefs"

    def review(self, ctx: ReviewContext) -> Verdict:
        # BERLIN's gate already ran the contract screen where one is wired up;
        # this reports what it found rather than paying for it twice.
        safety = ctx.safety
        if safety is None:
            return self._note("no structural report to brief from")
        contract_notes = [
            note for note in safety.checks_skipped if "contract" in note.lower()
        ]
        if contract_notes:
            return self._note(contract_notes[0])
        if ctx.pair.chain is Chain.ROBINHOOD:
            return self._pass(f"contract screen cleared at {safety.score}/100")
        return self._note("no contract-level screen configured for this chain")


class Rio(_BaseAgent):
    """Charts. Is there a move in progress worth joining?"""

    name = "RIO"
    role = "charts"

    def review(self, ctx: ReviewContext) -> Verdict:
        safety = ctx.safety or SafetyVerdict(passed=True, score=100)
        candidate = evaluate_entry(ctx.pair, safety, ctx.config.strategy)
        ctx.candidate = candidate
        if candidate.rejections:
            return self._veto(candidate.rejections[0], score=round(candidate.score, 3))
        top = sorted(candidate.components.items(), key=lambda kv: -kv[1])[:2]
        detail = ", ".join(f"{k.replace('_', ' ')} {v:.2f}" for k, v in top)
        return self._pass(
            f"score {candidate.score:.2f} — {detail}",
            score=round(candidate.score, 3),
            components={k: round(v, 3) for k, v in candidate.components.items()},
        )


class Helsinki(_BaseAgent):
    """The ledger. What does the book already say about this name?"""

    name = "HELSINKI"
    role = "ledger"

    def review(self, ctx: ReviewContext) -> Verdict:
        pair = ctx.pair
        if ctx.portfolio.holds(pair.chain, pair.base_address):
            return self._veto("already held; not adding")
        if pair.key in ctx.cooling_off:
            return self._veto("closed too recently — cooldown active")
        if not ctx.risk.chain_has_room(pair.chain, ctx.portfolio.open_positions):
            return self._veto(f"{pair.chain.label} already at its position limit")
        held = len(ctx.portfolio.open_positions)
        return self._pass(f"{held} open, no conflict on this name", open_positions=held)


class Stockholm(_BaseAgent):
    """Depth and slippage. Does execution eat the edge before it exists?

    This is the check that most paper strategies skip and most live ones die
    of. A round trip on a thin pool can cost a quarter of the stop distance,
    which means the trade needs a materially bigger move just to break even.
    """

    name = "STOCKHOLM"
    role = "depth"

    # A round trip may consume at most this share of the distance to the stop.
    MAX_COST_VS_STOP = 0.25

    def review(self, ctx: ReviewContext) -> Verdict:
        pair = ctx.pair
        price = pair.price_usd
        if not price:
            return self._veto("no price to size against")

        stop = initial_stop_price(price, ctx.config.strategy)
        sizing = size_position(
            equity_usd=ctx.portfolio.equity_usd,
            cash_usd=ctx.portfolio.cash_usd,
            entry_price=price,
            stop_price=stop,
            pair=pair,
            cfg=ctx.config.risk,
        )
        ctx.sizing, ctx.entry_price, ctx.stop_price = sizing, price, stop
        if not sizing.ok:
            return self._veto(sizing.rejected_reason or "cannot size this entry")

        cost = round_trip_cost_pct(
            sizing.usd_amount, pair.liquidity_usd, ctx.config.execution.dex_fee_pct
        )
        budget = ctx.config.strategy.stop_loss_pct * self.MAX_COST_VS_STOP
        if cost > budget:
            return self._veto(
                f"round trip costs {cost * 100:.1f}% — over "
                f"{self.MAX_COST_VS_STOP * 100:.0f}% of the "
                f"{ctx.config.strategy.stop_loss_pct * 100:.0f}% stop",
                round_trip_pct=round(cost, 5),
            )
        return self._pass(
            f"${sizing.usd_amount:.2f} costs {cost * 100:.2f}% round trip "
            f"({sizing.binding_constraint}-capped)",
            usd_amount=sizing.usd_amount,
            round_trip_pct=round(cost, 5),
        )


class Lisbon(_BaseAgent):
    """Freshness. Is the quote still the one everyone just voted on?

    Discovery, screening and scoring all take time, and a memecoin can move a
    long way in the seconds between the scan and the order. This re-quotes and
    vetoes if the price the committee approved is no longer the price on offer.
    """

    name = "LISBON"
    role = "recheck"

    MAX_DRIFT_PCT = 0.08

    def review(self, ctx: ReviewContext) -> Verdict:
        if ctx.feed is None or ctx.entry_price is None:
            return self._note("no feed to recheck against; using the scan quote")
        fresh = ctx.feed.get_pair(ctx.pair.chain, ctx.pair.base_address)
        if fresh is None or not fresh.price_usd:
            return self._veto("could not re-quote before entry")

        drift = fresh.price_usd / ctx.entry_price - 1
        if abs(drift) > self.MAX_DRIFT_PCT:
            return self._veto(
                f"price moved {drift * 100:+.1f}% since scoring", drift_pct=round(drift, 4)
            )
        # Adopt the fresh quote — this is the one the order will be sized on.
        ctx.pair = fresh
        ctx.entry_price = fresh.price_usd
        ctx.stop_price = initial_stop_price(fresh.price_usd, ctx.config.strategy)
        return self._pass(f"quote steady, {drift * 100:+.2f}% drift", drift_pct=round(drift, 4))


class Palermo(_BaseAgent):
    """Final approval, and the only question that matters at the end: can we get out?

    Everything before this asks whether the trade is worth entering. PALERMO
    asks whether the position could be sold if it were entered — at full size,
    into the depth that exists right now. A position you cannot exit is not a
    position, it is a donation.
    """

    name = "PALERMO"
    role = "approval"

    MAX_EXIT_IMPACT = 0.06

    def review(self, ctx: ReviewContext) -> Verdict:
        sizing, pair = ctx.sizing, ctx.pair
        if sizing is None or not sizing.ok:
            return self._veto("no approved size to authorise")
        if pair.liquidity_usd is None:
            return self._veto("exit depth unknown")

        exit_impact = sell_impact_pct(sizing.usd_amount, pair.liquidity_usd)
        if exit_impact > self.MAX_EXIT_IMPACT:
            return self._veto(
                f"exit too thin — selling ${sizing.usd_amount:.2f} would move price "
                f"{exit_impact * 100:.1f}%",
                exit_impact_pct=round(exit_impact, 5),
            )
        return self._pass(
            f"approved ${sizing.usd_amount:.2f}, exit costs {exit_impact * 100:.2f}%",
            usd_amount=sizing.usd_amount,
            exit_impact_pct=round(exit_impact, 5),
        )


# The running order. Cheap and local first, network and commitment last.
DEFAULT_ROSTER: tuple[Agent, ...] = (
    Professor(),
    Tokyo(),
    Berlin(),
    Denver(),
    Nairobi(),
    Rio(),
    Helsinki(),
    Stockholm(),
    Lisbon(),
    Palermo(),
)


class Committee:
    """Runs the roster over one candidate and records what each agent said."""

    def __init__(self, agents: Optional[tuple[Agent, ...]] = None):
        self.agents = agents or DEFAULT_ROSTER

    @property
    def roster(self) -> list[dict[str, str]]:
        return [{"name": a.name, "role": a.role} for a in self.agents]

    def review(self, ctx: ReviewContext) -> Review:
        review = Review(pair=ctx.pair)
        blocked = False
        for agent in self.agents:
            if blocked:
                review.verdicts.append(
                    Verdict(agent.name, agent.role, Stance.SKIPPED, "not consulted")
                )
                continue
            try:
                verdict = agent.review(ctx)
            except Exception as exc:  # noqa: BLE001
                # An agent that crashes must not approve by omission. A broken
                # check is an unanswered question, and unanswered questions
                # block the trade.
                verdict = Verdict(
                    agent.name, agent.role, Stance.VETO, f"check failed: {exc}"
                )
            review.verdicts.append(verdict)
            if verdict.blocking:
                blocked = True
        # ctx.pair may have been refreshed by LISBON; report what was approved.
        review.pair = ctx.pair
        review.score = ctx.candidate.score if ctx.candidate else 0.0
        review.entry_price = ctx.entry_price
        review.stop_price = ctx.stop_price
        review.approved_usd = ctx.sizing.usd_amount if ctx.sizing and ctx.sizing.ok else None
        return review
