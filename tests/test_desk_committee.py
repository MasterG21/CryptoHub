"""Each agent's job, and the veto structure that binds them."""
import pytest

from tests.factories import FakeFeed, make_hot_pair, make_pair
from trading_desk.committee import (
    DEFAULT_ROSTER,
    Berlin,
    Committee,
    Denver,
    Helsinki,
    Lisbon,
    Nairobi,
    Palermo,
    Professor,
    ReviewContext,
    Rio,
    Stance,
    Stockholm,
    Tokyo,

)
from trading_desk.config import DeskConfig
from trading_desk.marketdata.base import MultiChainFeed
from trading_desk.marketdata.history import PriceHistory
from trading_desk.models import Chain, TxnCounts
from trading_desk.portfolio import Portfolio
from trading_desk.risk import RiskManager
from trading_desk.safety import SafetyGate


def make_ctx(pair=None, portfolio=None, cfg=None, cooling_off=None, feed=None):
    cfg = cfg or DeskConfig()
    cfg.chains = (Chain.SOLANA,)
    portfolio = portfolio or Portfolio(100.0)
    risk = RiskManager(cfg.risk)
    risk.sync_day(portfolio.equity_usd)
    return ReviewContext(
        pair=pair or make_hot_pair(),
        config=cfg,
        portfolio=portfolio,
        risk=risk,
        safety_gate=SafetyGate(cfg.safety),
        history=PriceHistory(),
        cooling_off=cooling_off or set(),
        feed=feed,
    )


def run_to(ctx, *agents):
    """Run agents in order, returning the last verdict."""
    verdict = None
    for agent in agents:
        verdict = agent.review(ctx)
    return verdict


# -------------------------------------------------------------------- roster


def test_the_roster_is_ten_named_specialists():
    names = [a.name for a in DEFAULT_ROSTER]
    assert len(names) == 10
    assert len(set(names)) == 10
    assert names[0] == "PROFESSOR"  # mandate first
    assert names[-1] == "PALERMO"  # exit depth last


def test_every_agent_has_a_distinct_role():
    roles = [a.role for a in DEFAULT_ROSTER]
    assert len(set(roles)) == len(roles)


# -------------------------------------------------------------------- agents


def test_professor_vetoes_when_the_desk_is_halted():
    ctx = make_ctx()
    ctx.risk.state.consecutive_losses = 99
    assert Professor().review(ctx).stance is Stance.VETO


def test_professor_vetoes_a_chain_outside_the_mandate():
    ctx = make_ctx(pair=make_hot_pair(chain=Chain.BNB))
    assert "not in the mandate" in Professor().review(ctx).reason


def test_professor_vetoes_when_every_slot_is_taken():
    cfg = DeskConfig()
    cfg.risk.max_concurrent_positions = 1
    portfolio = Portfolio(100.0)
    ctx = make_ctx(cfg=cfg, portfolio=portfolio)
    ctx.portfolio.positions["solana:x"] = _dummy_position()
    assert "no position slots free" in Professor().review(ctx).reason


def _dummy_position():
    from trading_desk.models import Position

    return Position(
        chain=Chain.SOLANA, token_address="X", symbol="X", quantity=1.0,
        avg_entry_price=1.0, cost_basis_usd=1.0, stop_price=0.7,
    )


def test_tokyo_vetoes_an_unpriceable_pair():
    ctx = make_ctx(pair=make_pair(price_usd=None))
    assert Tokyo().review(ctx).stance is Stance.VETO


def test_berlin_vetoes_on_structure_and_records_the_verdict():
    ctx = make_ctx(pair=make_hot_pair(liquidity_usd=3_000))
    verdict = Berlin().review(ctx)
    assert verdict.stance is Stance.VETO
    assert "below floor" in verdict.reason
    assert ctx.safety is not None  # cached for later agents


def test_denver_vetoes_manufactured_turnover():
    """64x the pool's depth in an hour is inventory being cycled, not demand."""
    ctx = make_ctx(pair=make_hot_pair(liquidity_usd=22_000, volume_1h=1_400_000))
    verdict = Denver().review(ctx)
    assert verdict.stance is Stance.VETO
    assert "manufactured" in verdict.reason


def test_denver_vetoes_volume_carried_by_a_handful_of_trades():
    ctx = make_ctx(pair=make_hot_pair(volume_1h=40_000, txns_1h=TxnCounts(buys=5, sells=3)))
    assert Denver().review(ctx).stance is Stance.VETO


def test_denver_passes_ordinary_activity():
    assert Denver().review(make_ctx()).stance is Stance.PASS


def test_nairobi_reports_rather_than_re_running_the_contract_screen():
    ctx = make_ctx()
    Berlin().review(ctx)
    assert Nairobi().review(ctx).stance in (Stance.PASS, Stance.NOTE)


def test_rio_vetoes_a_weak_score_and_passes_a_strong_one():
    weak = make_ctx(pair=make_pair())
    Berlin().review(weak)
    assert Rio().review(weak).stance is Stance.VETO

    strong = make_ctx(pair=make_hot_pair())
    Berlin().review(strong)
    verdict = Rio().review(strong)
    assert verdict.stance is Stance.PASS
    assert verdict.data["score"] >= 0.55


def test_helsinki_vetoes_a_name_already_held():
    portfolio = Portfolio(100.0)
    pair = make_hot_pair()
    portfolio.positions[pair.key] = _dummy_position()
    ctx = make_ctx(pair=pair, portfolio=portfolio)
    ctx.portfolio.positions[pair.key].token_address = pair.base_address
    assert "already held" in Helsinki().review(ctx).reason


def test_helsinki_vetoes_a_name_in_cooldown():
    pair = make_hot_pair()
    ctx = make_ctx(pair=pair, cooling_off={pair.key})
    assert "cooldown" in Helsinki().review(ctx).reason


def test_stockholm_vetoes_when_the_round_trip_eats_the_stop():
    """A position large enough, in a pool thin enough, that execution costs
    more than a quarter of the distance to the stop. On $100 nothing strains a
    $16k pool — it takes an account big enough for the risk budget to bite."""
    cfg = DeskConfig()
    cfg.risk.max_pool_impact_pct = 0.5  # let sizing through so cost is what binds
    ctx = make_ctx(
        pair=make_hot_pair(liquidity_usd=16_000), cfg=cfg, portfolio=Portfolio(10_000.0)
    )
    verdict = Stockholm().review(ctx)
    assert verdict.stance is Stance.VETO
    assert "round trip" in verdict.reason


def test_stockholm_passes_a_deep_pool_and_records_the_size():
    ctx = make_ctx(pair=make_hot_pair(liquidity_usd=400_000))
    verdict = Stockholm().review(ctx)
    assert verdict.stance is Stance.PASS
    assert ctx.sizing is not None and ctx.sizing.ok
    assert verdict.data["usd_amount"] > 0


def test_lisbon_vetoes_when_the_price_ran_away_before_entry():
    pair = make_hot_pair()
    feed = MultiChainFeed([FakeFeed(pairs=[pair])])
    ctx = make_ctx(pair=pair, feed=feed)
    ctx.entry_price = pair.price_usd
    pair.price_usd *= 1.30  # moved 30% between scoring and entry

    verdict = Lisbon().review(ctx)
    assert verdict.stance is Stance.VETO
    assert "moved" in verdict.reason


def test_lisbon_adopts_the_fresh_quote_when_drift_is_small():
    pair = make_hot_pair()
    feed = MultiChainFeed([FakeFeed(pairs=[pair])])
    ctx = make_ctx(pair=pair, feed=feed)
    ctx.entry_price = pair.price_usd
    pair.price_usd *= 1.02

    assert Lisbon().review(ctx).stance is Stance.PASS
    assert ctx.entry_price == pytest.approx(pair.price_usd)
    assert ctx.stop_price == pytest.approx(pair.price_usd * 0.7)


def test_lisbon_vetoes_when_it_cannot_re_quote():
    feed = MultiChainFeed([FakeFeed(pairs=[])])
    ctx = make_ctx(feed=feed)
    ctx.entry_price = 0.001
    assert "could not re-quote" in Lisbon().review(ctx).reason


def test_palermo_vetoes_when_the_exit_would_move_the_price_too_far():
    cfg = DeskConfig()
    cfg.risk.max_pool_impact_pct = 0.9  # force a size the pool cannot absorb
    cfg.risk.max_position_pct = 1.0
    ctx = make_ctx(
        pair=make_hot_pair(liquidity_usd=18_000), cfg=cfg, portfolio=Portfolio(10_000.0)
    )
    Stockholm().review(ctx)  # sets the size PALERMO is asked to authorise

    verdict = Palermo().review(ctx)
    assert verdict.stance is Stance.VETO
    assert "exit too thin" in verdict.reason


def test_palermo_approves_a_position_it_could_sell():
    ctx = make_ctx(pair=make_hot_pair(liquidity_usd=400_000))
    Stockholm().review(ctx)
    verdict = Palermo().review(ctx)
    assert verdict.stance is Stance.PASS
    assert verdict.data["exit_impact_pct"] < 0.06


# ----------------------------------------------------------------- committee


def test_a_clean_candidate_clears_all_ten():
    feed = MultiChainFeed([FakeFeed(pairs=[make_hot_pair(liquidity_usd=400_000)])])
    ctx = make_ctx(pair=make_hot_pair(liquidity_usd=400_000), feed=feed)
    review = Committee().review(ctx)

    assert review.approved
    assert review.blocked_by is None
    assert len(review.consulted) == 10
    assert review.approved_usd and review.approved_usd > 0
    # NAIROBI notes that Solana has no contract-level screen wired up. A note
    # is not a veto: the trade is approved and the remark is surfaced.
    assert review.summary.startswith("NAIROBI:")
    assert all(v.stance is not Stance.VETO for v in review.verdicts)


def test_one_veto_blocks_and_the_rest_are_not_consulted():
    ctx = make_ctx(pair=make_hot_pair(liquidity_usd=3_000))
    review = Committee().review(ctx)

    assert not review.approved
    assert review.blocked_by.agent == "BERLIN"
    skipped = [v for v in review.verdicts if v.stance is Stance.SKIPPED]
    assert [v.agent for v in skipped] == ["DENVER", "NAIROBI", "RIO", "HELSINKI",
                                          "STOCKHOLM", "LISBON", "PALERMO"]


def test_a_crashing_agent_blocks_rather_than_approving_by_omission():
    """An unanswered question is not a yes."""

    class Broken:
        name = "BROKEN"
        role = "explodes"

        def review(self, ctx):
            raise RuntimeError("upstream is down")

    review = Committee(agents=(Broken(),)).review(make_ctx())
    assert not review.approved
    assert review.blocked_by.agent == "BROKEN"
    assert "check failed" in review.blocked_by.reason


def test_every_verdict_is_reported_even_the_skipped_ones():
    review = Committee().review(make_ctx(pair=make_hot_pair(liquidity_usd=3_000)))
    assert len(review.verdicts) == 10  # the full roster is always accounted for


def test_the_review_serialises_for_the_dashboard():
    payload = Committee().review(make_ctx()).to_dict()
    assert set(payload) >= {"symbol", "chain", "approved", "summary", "verdicts", "score"}
    assert len(payload["verdicts"]) == 10
    assert all({"agent", "role", "stance", "reason"} <= set(v) for v in payload["verdicts"])
