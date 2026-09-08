"""The dashboard: snapshot shape, controls, and the isolation between them.

The web layer must never be able to interleave with position management, so
control requests are queued for the trading thread rather than executed on the
request thread. These tests drive the runner directly, without threads, so the
assertions are deterministic.
"""
import json
import os
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


# ------------------------------------------------------------------ settings


@pytest.fixture
def settings_paths(tmp_path):
    config = tmp_path / "desk.config.json"
    config.write_text('{"starting_capital_usd": 100.0}')
    return config, tmp_path / ".env"


def test_settings_report_the_current_config(settings_paths):
    from trading_desk.web.settings import read_settings

    config, env = settings_paths
    out = read_settings(DeskConfig(), config, env)

    assert out["mode"] == "paper"
    assert out["preset"] == "normal"
    assert len(out["presets"]) == 3
    assert [p["id"] for p in out["presets"]] == ["cautious", "normal", "bold"]


def test_settings_never_return_key_material(settings_paths, monkeypatch):
    """An open dashboard tab must not be able to read the wallet."""
    from trading_desk.execution.signers import EVM_KEY_ENV
    from trading_desk.web.settings import read_settings

    secret = "0x" + "ab" * 32
    monkeypatch.setenv(EVM_KEY_ENV, secret)
    config, env = settings_paths
    out = read_settings(DeskConfig(), config, env)

    assert out["keys"]["evm"] is True
    assert secret not in json.dumps(out)


def test_a_preset_applies_to_the_running_desk_immediately(settings_paths):
    from trading_desk.web.settings import write_settings

    config, env = settings_paths
    cfg = DeskConfig()
    result = write_settings({"preset": "cautious"}, cfg, config, env)

    assert result["ok"] and result["applied_now"]
    assert cfg.risk.risk_per_trade_pct == 0.01
    assert cfg.strategy.stop_loss_pct == 0.25
    assert json.loads(config.read_text())["risk"]["risk_per_trade_pct"] == 0.01


def test_mode_and_capital_changes_ask_for_a_restart(settings_paths):
    from trading_desk.web.settings import write_settings

    config, env = settings_paths
    result = write_settings(
        {"mode": "live", "starting_capital_usd": 500}, DeskConfig(), config, env
    )

    assert set(result["needs_restart"]) == {"mode", "starting_capital_usd"}
    stored = json.loads(config.read_text())
    assert stored["execution"]["mode"] == "live"
    # Choosing live here flips the second switch; --arm is still required.
    assert stored["execution"]["allow_live_trading"] is True


def test_bad_settings_are_refused_with_plain_reasons(settings_paths):
    from trading_desk.web.settings import write_settings

    config, env = settings_paths
    result = write_settings(
        {"starting_capital_usd": -5, "chains": ["dogechain"], "preset": "reckless"},
        DeskConfig(), config, env,
    )

    assert result["ok"] is False
    assert len(result["problems"]) == 3
    assert any("more than zero" in p for p in result["problems"])


def test_keys_are_written_with_owner_only_permissions(settings_paths, monkeypatch):
    import platform

    from trading_desk.execution.signers import EVM_KEY_ENV
    from trading_desk.web.settings import write_settings

    monkeypatch.delenv(EVM_KEY_ENV, raising=False)
    config, env = settings_paths
    result = write_settings({"evm_key": "0x" + "cd" * 32}, DeskConfig(), config, env)

    assert "wallet keys" in result["needs_restart"]
    assert env.exists()
    assert os.environ[EVM_KEY_ENV] == "0x" + "cd" * 32
    if platform.system() != "Windows":
        assert oct(env.stat().st_mode)[-3:] == "600"


def test_an_empty_key_clears_it(settings_paths, monkeypatch):
    from trading_desk.execution.signers import EVM_KEY_ENV
    from trading_desk.web.settings import write_settings

    config, env = settings_paths
    write_settings({"evm_key": "0x" + "ef" * 32}, DeskConfig(), config, env)
    write_settings({"evm_key": ""}, DeskConfig(), config, env)

    assert EVM_KEY_ENV not in os.environ
    assert "ef" * 32 not in env.read_text()


def test_the_closed_settings_sheet_cannot_swallow_clicks():
    """`display: flex` outranks [hidden], so the rule below must exist.

    Without it the closed overlay stays laid out, invisible and full-screen,
    and every click on Pause or Flatten all lands on it instead.
    """
    from pathlib import Path

    page = (Path("trading_desk/web/static/index.html")).read_text()
    assert ".sheet[hidden] { display: none; }" in page


# --------------------------------------------- recovery from a stuck config


def test_the_dashboard_starts_even_when_live_mode_is_misconfigured(tmp_path):
    """The single worst bug this had: choosing "Real money" with no wallet key
    made `serve` exit before starting the dashboard — and the dashboard is the
    only place that setting can be changed back. One click locked the operator
    out with no route to paper mode."""
    from trading_desk.cli import build_parser

    config = tmp_path / "desk.config.json"
    config.write_text(json.dumps({
        "starting_capital_usd": 100.0,
        "chains": ["solana"],
        "execution": {"mode": "live", "allow_live_trading": True},
    }))

    args = build_parser().parse_args(
        ["-c", str(config), "serve", "--port", "0", "--interval", "3600"]
    )
    # cmd_serve blocks on the runner, so assert the gate itself is gone: the
    # code path that used to `return 1` before serving no longer exists.
    from pathlib import Path

    source = Path("trading_desk/cli.py").read_text()
    gate = source.split("def cmd_serve")[1].split("runner = DeskRunner")[0]
    assert "return 1" not in gate
    assert "desk.paused = True" in gate
    assert args.port == 0


def test_unarmed_live_mode_reports_blockers_and_refuses_to_trade():
    from trading_desk.execution.live import LiveExecutor

    cfg = DeskConfig()
    cfg.chains = (Chain.SOLANA,)
    cfg.execution.mode = "live"
    cfg.execution.allow_live_trading = True
    desk = TradingDesk(cfg, MultiChainFeed([FakeFeed(pairs=[make_hot_pair()])]),
                       LiveExecutor(cfg))
    desk.paused = True  # what cmd_serve now does when preflight reports blockers

    state = DeskRunner(desk).snapshot()["mode"]
    assert state["can_trade"] is False
    assert state["blockers"]
    assert state["paused"] is True


def test_switching_back_to_paper_also_clears_the_live_switch(tmp_path):
    """Leaving allow_live_trading set would re-arm the next accidental flip."""
    from trading_desk.web.settings import write_settings

    config = tmp_path / "desk.config.json"
    config.write_text(json.dumps({"execution": {"mode": "live", "allow_live_trading": True}}))
    cfg = DeskConfig()
    cfg.execution.mode = "live"
    cfg.execution.allow_live_trading = True

    result = write_settings({"mode": "paper"}, cfg, config, tmp_path / ".env")

    assert result["ok"]
    stored = json.loads(config.read_text())["execution"]
    assert stored["mode"] == "paper"
    assert stored["allow_live_trading"] is False
    assert cfg.execution.allow_live_trading is False


def test_a_busy_port_falls_back_instead_of_crashing():
    """A previous run still holding the port must not be a fatal error."""
    import socket

    from trading_desk.web.server import serve

    cfg = DeskConfig()
    cfg.chains = (Chain.SOLANA,)
    cfg.poll_interval_seconds = 3600
    desk = TradingDesk(cfg, MultiChainFeed([FakeFeed(pairs=[])]), PaperExecutor(cfg))

    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    taken = blocker.getsockname()[1]

    runner = DeskRunner(desk)
    httpd = serve(runner, port=taken)
    try:
        assert httpd.server_address[1] != taken
        assert httpd.server_address[1] > taken
    finally:
        httpd.shutdown()
        runner.stop()
        blocker.close()


def test_the_recovery_banner_offers_the_fix_not_just_the_diagnosis():
    from pathlib import Path

    page = Path("trading_desk/web/static/index.html").read_text()
    assert "switchToPractice" in page
    assert "Switch back to practice mode" in page


def test_changing_the_practice_budget_actually_takes_effect(tmp_path):
    """Writing the number to a file was not enough: the journal's saved balance
    won on every load, so the setting silently did nothing, restart or not."""
    from trading_desk.journal import Journal
    from trading_desk.web.settings import write_settings

    cfg = DeskConfig()
    cfg.chains = (Chain.SOLANA,)
    cfg.journal_path = str(tmp_path / "j.sqlite3")
    journal = Journal(cfg.journal_path)
    desk = TradingDesk(cfg, MultiChainFeed([FakeFeed(pairs=[make_hot_pair()])]),
                       PaperExecutor(cfg), journal=journal)
    desk.tick()
    assert desk.portfolio.open_positions  # a book exists before the change

    config = tmp_path / "desk.config.json"
    config.write_text("{}")
    result = write_settings(
        {"starting_capital_usd": 1000}, cfg, config, tmp_path / ".env", desk=desk
    )

    assert result["ok"] and result["account_reset"] is True
    assert result["needs_restart"] == []  # no restart needed, it is applied
    assert desk.portfolio.starting_cash_usd == 1000
    assert desk.portfolio.cash_usd == 1000
    assert desk.portfolio.open_positions == []
    assert desk.portfolio.closed_trades == []

    # And it survives a reload, rather than the old balance coming back.
    assert journal.load_portfolio(1000).cash_usd == 1000
    journal.close()


def test_the_budget_change_persists_across_a_restart(tmp_path):
    from trading_desk.journal import Journal
    from trading_desk.web.settings import write_settings

    cfg = DeskConfig()
    cfg.chains = (Chain.SOLANA,)
    cfg.journal_path = str(tmp_path / "j.sqlite3")
    journal = Journal(cfg.journal_path)
    desk = TradingDesk(cfg, MultiChainFeed([FakeFeed(pairs=[])]), PaperExecutor(cfg),
                       journal=journal)
    config = tmp_path / "desk.config.json"
    config.write_text("{}")
    write_settings({"starting_capital_usd": 1000}, cfg, config, tmp_path / ".env", desk=desk)
    journal.close()

    reopened = Journal(cfg.journal_path)
    restored = reopened.load_portfolio(100.0)  # config default must not win back
    assert restored.starting_cash_usd == 1000
    assert restored.cash_usd == 1000
    reopened.close()


class _StubSigner:
    def sign_and_send(self, chain, payload):
        raise AssertionError("no order should be placed in these tests")

    def wallet_address(self, chain):
        return "0xwallet"


def test_a_live_budget_change_is_not_silently_applied_to_a_real_book(tmp_path):
    """Wiping a real account's history because a number was edited would be wrong.

    The test is what makes it real: a fully armed live executor, since an
    unarmed one has never placed an order and is safe to reset.
    """
    from trading_desk.execution.live import LiveExecutor
    from trading_desk.web.settings import write_settings

    cfg = DeskConfig()
    cfg.chains = (Chain.SOLANA,)
    cfg.execution.mode = "live"
    cfg.execution.allow_live_trading = True
    executor = LiveExecutor(cfg, signer=_StubSigner())
    assert executor.preflight() == []  # genuinely armed

    desk = TradingDesk(cfg, MultiChainFeed([FakeFeed(pairs=[])]), executor)
    config = tmp_path / "desk.config.json"
    config.write_text("{}")

    result = write_settings(
        {"starting_capital_usd": 5000}, cfg, config, tmp_path / ".env", desk=desk
    )

    assert result["account_reset"] is False
    assert "starting_capital_usd" in result["needs_restart"]
    assert desk.portfolio.starting_cash_usd == 100.0


def test_an_unarmed_live_desk_can_still_be_reset(tmp_path):
    """It has never placed an order, so its account is pretend either way."""
    from trading_desk.execution.live import LiveExecutor
    from trading_desk.web.settings import write_settings

    cfg = DeskConfig()
    cfg.chains = (Chain.SOLANA,)
    cfg.execution.mode = "live"
    desk = TradingDesk(cfg, MultiChainFeed([FakeFeed(pairs=[])]), LiveExecutor(cfg))
    config = tmp_path / "desk.config.json"
    config.write_text("{}")

    result = write_settings(
        {"starting_capital_usd": 1000}, cfg, config, tmp_path / ".env", desk=desk
    )

    assert result["account_reset"] is True
    assert desk.portfolio.starting_cash_usd == 1000


def test_switching_to_practice_takes_effect_without_a_restart(tmp_path):
    """Requiring a restart to escape a broken live setup is how people stay stuck."""
    from trading_desk.execution.live import LiveExecutor
    from trading_desk.execution.paper import PaperExecutor as Paper
    from trading_desk.web.settings import write_settings

    cfg = DeskConfig()
    cfg.chains = (Chain.SOLANA,)
    cfg.execution.mode = "live"
    desk = TradingDesk(cfg, MultiChainFeed([FakeFeed(pairs=[])]), LiveExecutor(cfg))
    desk.paused = True
    config = tmp_path / "desk.config.json"
    config.write_text("{}")

    result = write_settings({"mode": "paper"}, cfg, config, tmp_path / ".env", desk=desk)

    assert result["needs_restart"] == []
    assert isinstance(desk.executor, Paper)
    assert cfg.execution.mode == "paper"
    assert desk.paused is False
