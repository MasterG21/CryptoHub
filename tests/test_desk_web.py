"""The dashboard: snapshot shape, controls, and the isolation between them.

The web layer must never be able to interleave with position management, so
control requests are queued for the trading thread rather than executed on the
request thread. These tests drive the runner directly, without threads, so the
assertions are deterministic.
"""
import json
import threading
import urllib.error
import urllib.request

import pytest

from tests.factories import FakeFeed, make_hot_pair, make_pair
from trading_desk.config import DeskConfig
from trading_desk.desk import TradingDesk
from trading_desk.execution.paper import PaperExecutor
from trading_desk.marketdata.base import MultiChainFeed
from trading_desk.models import Chain
from trading_desk.web.runner import DeskRunner
from trading_desk.web.server import make_server


@pytest.fixture
def runner():
    cfg = DeskConfig(poll_interval_seconds=1)
    cfg.chains = (Chain.SOLANA,)
    feed = FakeFeed(pairs=[make_hot_pair(liquidity_usd=400_000), make_pair(
        base_address="TK2", base_symbol="THIN", pair_address="P2", liquidity_usd=2_000)])
    desk = TradingDesk(
        config=cfg,
        feed=MultiChainFeed([feed]),
        executor=PaperExecutor(cfg),
        journal=None,
    )
    runner = DeskRunner(desk)
    runner.desk.tick()  # one tick synchronously, so there is state to report
    runner._record(runner.desk.tick())
    runner._last_tick = runner.desk._last_tick if hasattr(runner.desk, "_last_tick") else None
    return runner, desk, feed


# ------------------------------------------------------------------ snapshot


def test_snapshot_has_every_panel_the_dashboard_reads(runner):
    run, desk, _ = runner
    run._last_tick = desk.tick()
    state = run.snapshot()

    assert set(state) >= {
        "mode", "equity", "performance", "risk", "tick",
        "positions", "agents", "reviews", "activity", "trades", "equity_curve",
    }
    assert state["mode"]["execution"] == "paper"
    assert state["mode"]["armed"] is False


def test_snapshot_is_json_serialisable(runner):
    run, desk, _ = runner
    run._last_tick = desk.tick()
    assert json.loads(json.dumps(run.snapshot(), default=str))


def test_the_roster_is_always_reported_even_before_the_first_tick():
    cfg = DeskConfig()
    cfg.chains = (Chain.SOLANA,)
    desk = TradingDesk(cfg, MultiChainFeed([FakeFeed(pairs=[])]), PaperExecutor(cfg))
    agents = DeskRunner(desk).snapshot()["agents"]

    assert len(agents) == 10
    assert all(a["passed"] == 0 and a["vetoed"] == 0 for a in agents)
    assert [a["name"] for a in agents][0] == "PROFESSOR"


def test_agent_tallies_reflect_the_last_tick(runner):
    run, desk, _ = runner
    run._last_tick = desk.tick()
    by_name = {a["name"]: a for a in run.snapshot()["agents"]}

    # The thin pool is refused on structure; BERLIN is the agent that says so.
    assert by_name["BERLIN"]["vetoed"] >= 1
    assert by_name["BERLIN"]["last"]
    # Agents after a veto are recorded as never consulted, not as passing.
    assert by_name["PALERMO"]["skipped"] >= 1


def test_the_untradeable_floor_is_reported(runner):
    run, desk, _ = runner
    equity = run.snapshot()["equity"]

    # $5 minimum across a 30% stop at 2% risk cannot be funded below $75.
    assert equity["untradeable_below_usd"] == pytest.approx(75.0)
    assert 0 < equity["room_to_floor_pct"] < 1


def test_positions_and_reviews_appear_after_a_tick(runner):
    run, desk, _ = runner
    run._last_tick = desk.tick()
    state = run.snapshot()

    assert len(state["positions"]) >= 1
    assert state["positions"][0]["symbol"] == "DOGE"
    assert any(not r["approved"] for r in state["reviews"])


# ------------------------------------------------------------------ controls


def test_pause_stops_entries_but_not_exits(runner):
    run, desk, feed = runner
    run.pause()
    assert desk.paused

    result = desk.tick()
    assert result.entries == []
    assert result.halted_reason == "paused by operator"

    # The open position still gets managed while paused.
    feed.set_price("TOKEN1", 0.0004)
    result = desk.tick()
    assert any("stop-loss" in e for e in result.exits)


def test_resume_clears_the_pause_and_the_halt(runner):
    run, desk, _ = runner
    run.pause()
    run.resume()

    assert desk.paused is False
    assert desk.risk.state.halted_reason is None


def test_panic_is_queued_for_the_trading_thread_not_run_inline(runner):
    """The web thread must never touch positions directly."""
    run, desk, _ = runner
    open_before = len(desk.portfolio.open_positions)
    assert open_before >= 1

    run.panic()
    assert run._panic_requested is True
    assert len(desk.portfolio.open_positions) == open_before  # nothing yet

    run._run_panic()  # what the trading thread does on its next pass
    assert desk.portfolio.open_positions == []
    assert desk.paused is True


def test_activity_records_who_vetoed_what(runner):
    run, desk, _ = runner
    run._record(desk.tick())
    vetoes = [a for a in run._activity if a["kind"] == "veto"]

    assert vetoes
    assert vetoes[0]["agent"]
    assert "THIN" in " ".join(a["message"] for a in vetoes)


def test_the_activity_log_is_bounded():
    cfg = DeskConfig()
    cfg.chains = (Chain.SOLANA,)
    desk = TradingDesk(cfg, MultiChainFeed([FakeFeed(pairs=[])]), PaperExecutor(cfg))
    run = DeskRunner(desk, activity_limit=5)
    for i in range(50):
        run._log("note", f"line {i}")
    assert len(run._activity) == 5


# -------------------------------------------------------------- HTTP surface


@pytest.fixture
def server(runner):
    run, _, _ = runner
    httpd = make_server(run, port=0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", run
    httpd.shutdown()


def get(url):
    with urllib.request.urlopen(url, timeout=5) as response:
        return response.status, response.read()


def post(url, payload):
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_the_page_is_served(server):
    base, _ = server
    status, body = get(base + "/")
    assert status == 200
    assert b"TRADING DESK" in body
    assert b"committee" in body.lower()


def test_the_state_endpoint_returns_the_snapshot(server):
    base, _ = server
    status, body = get(base + "/api/state")
    assert status == 200
    assert "equity" in json.loads(body)


def test_unknown_routes_404(server):
    base, _ = server
    with pytest.raises(urllib.error.HTTPError) as exc:
        get(base + "/api/nope")
    assert exc.value.code == 404


def test_control_actions_are_accepted(server):
    base, run = server
    assert post(base + "/api/control", {"action": "pause"}) == (200, {"status": "paused"})
    assert run.desk.paused is True
    assert post(base + "/api/control", {"action": "resume"}) == (200, {"status": "running"})
    assert run.desk.paused is False


def test_an_unknown_control_action_is_rejected(server):
    base, _ = server
    status, payload = post(base + "/api/control", {"action": "sell_everything_lol"})
    assert status == 400
    assert "allowed" in payload


def test_malformed_control_bodies_are_rejected(server):
    base, _ = server
    request = urllib.request.Request(
        base + "/api/control", data=b"{not json",
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(request, timeout=5)
    assert exc.value.code == 400


def test_an_unchanged_verdict_is_logged_once_not_every_tick(runner):
    """Fifty ticks of the same refusal must not bury the log."""
    run, desk, _ = runner
    run._activity.clear()
    run._last_decision.clear()

    for _ in range(5):
        run._record(desk.tick())

    thin = [a for a in run._activity if "THIN" in a["message"]]
    assert len(thin) == 1


def test_a_changed_verdict_is_logged_again(runner):
    run, desk, feed = runner
    run._activity.clear()
    run._last_decision.clear()
    run._record(desk.tick())
    before = len([a for a in run._activity if "THIN" in a["message"]])

    # Deepen the pool so THIN clears BERLIN and is refused by someone else.
    feed.set_price("TK2", 0.001, liquidity=400_000)
    run._record(desk.tick())

    after = len([a for a in run._activity if "THIN" in a["message"]])
    assert after > before
