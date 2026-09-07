"""CLI wiring, with the market-data layer replaced by canned pairs.

These exercise argument parsing, command dispatch and output shape. Nothing
here touches the network: this environment has no route to DexScreener,
Blockscout or any RPC, so the feeds are swapped for fakes at the seam the CLI
builds them at.
"""
import json
import os
import re
import tempfile

import pytest

from tests.factories import FakeFeed, make_hot_pair, make_pair
from trading_desk import cli
from trading_desk.marketdata.base import MultiChainFeed


ANSI = re.compile(r"\x1b\[[0-9;]*m")


def plain(text: str) -> str:
    """Strip the colour codes so assertions match on the words, not the escapes."""
    return ANSI.sub("", text)


@pytest.fixture
def fake_feeds(monkeypatch):
    """Replace the CLI's feed factory with one serving canned pairs."""
    pairs = [
        make_hot_pair(),
        make_pair(base_address="TOKEN2", base_symbol="CAT", pair_address="POOL2"),
        make_pair(base_address="TOKEN3", base_symbol="RUG", pair_address="POOL3", liquidity_usd=900),
    ]
    feed = FakeFeed(pairs=pairs)
    monkeypatch.setattr(cli, "build_feed", lambda cfg, args, history: MultiChainFeed([feed]))
    return feed


@pytest.fixture
def journal_path():
    with tempfile.TemporaryDirectory() as directory:
        yield os.path.join(directory, "journal.sqlite3")


def test_plan_reports_the_target_and_the_math(capsys):
    assert cli.main(["plan", "--runs", "200", "--trades", "300"]) == 0
    out = capsys.readouterr().out

    assert "10,000x" in out
    assert "Growth-optimal (full Kelly)" in out
    assert "The small-account problem" in out
    assert "Everything depends on the tail" in out
    assert "Monte Carlo" in out


def test_plan_states_plainly_when_the_target_is_unreachable(capsys):
    assert cli.main(["plan", "--runs", "100", "--trades", "100"]) == 0
    assert "compounds downward" in capsys.readouterr().out


def test_simulate_emits_json(capsys):
    assert cli.main(["--json", "simulate", "--runs", "200", "--trades", "200"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["runs"] == 200
    assert 0.0 <= payload["p_ruin"] <= 1.0
    assert "median_equity" in payload


def test_simulate_honours_a_risk_override(capsys):
    cli.main(["--json", "simulate", "--runs", "300", "--trades", "300", "--risk", "0.5"])
    reckless = json.loads(capsys.readouterr().out)
    cli.main(["--json", "simulate", "--runs", "300", "--trades", "300", "--risk", "0.005"])
    careful = json.loads(capsys.readouterr().out)

    assert reckless["p_ruin"] > careful["p_ruin"]


def test_scan_ranks_candidates(fake_feeds, capsys):
    assert cli.main(["--chains", "solana", "scan"]) == 0
    out = capsys.readouterr().out

    assert "Scanned 3 pairs" in out
    assert "DOGE" in out
    assert "TRADEABLE" in out


def test_scan_json_reports_why_each_pair_was_refused(fake_feeds, capsys):
    assert cli.main(["--chains", "solana", "--json", "scan", "--all"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["scanned"] == 3
    assert payload["safety_rejected"] == 1
    by_symbol = {c["symbol"]: c for c in payload["candidates"]}
    assert by_symbol["DOGE"]["tradeable"]
    assert not by_symbol["RUG"]["tradeable"]
    assert by_symbol["RUG"]["safety_rejections"]


def test_run_executes_ticks_and_reports_the_session(fake_feeds, capsys):
    assert cli.main(["--chains", "solana", "--no-journal", "run", "--ticks", "2", "--interval", "0"]) == 0
    out = plain(capsys.readouterr().out)

    assert "mode=paper" in out
    assert "BUY" in out
    assert "Session over" in out
    assert "Closed trades" in out


def test_run_warns_about_overbetting_before_it_starts(fake_feeds, capsys):
    cli.main(["--chains", "solana", "--no-journal", "run", "--ticks", "1", "--interval", "0"])
    assert "Risk warning" in capsys.readouterr().out


def test_run_refuses_live_mode_without_a_signer(fake_feeds, capsys):
    assert cli.main(["--chains", "solana", "--no-journal", "run", "--ticks", "1", "--interval", "0", "--live"]) == 1
    out = capsys.readouterr().out

    assert "Live mode is not armed" in out
    assert "no TransactionSigner supplied" in out


def test_run_then_status_reads_back_the_session(fake_feeds, journal_path, capsys):
    cli.main(["--chains", "solana", "--journal", journal_path, "run", "--ticks", "2", "--interval", "0"])
    capsys.readouterr()

    assert cli.main(["--journal", journal_path, "status"]) == 0
    out = capsys.readouterr().out
    assert "Portfolio" in out
    assert "Open positions" in out
    assert "Remaining to target" in out


def test_status_json(fake_feeds, journal_path, capsys):
    cli.main(["--chains", "solana", "--journal", journal_path, "run", "--ticks", "1", "--interval", "0"])
    capsys.readouterr()

    cli.main(["--journal", journal_path, "--json", "status"])
    payload = json.loads(capsys.readouterr().out)
    assert "equity_usd" in payload
    assert "max_drawdown_pct" in payload


def test_panic_flattens_the_book(fake_feeds, journal_path, capsys):
    cli.main(["--chains", "solana", "--journal", journal_path, "run", "--ticks", "1", "--interval", "0"])
    capsys.readouterr()

    assert cli.main(["--chains", "solana", "--journal", journal_path, "panic"]) == 0
    assert "Flattening" in capsys.readouterr().out

    cli.main(["--journal", journal_path, "--json", "status"])
    assert json.loads(capsys.readouterr().out)["open_positions"] == 0


def test_doctor_passes_on_defaults(capsys):
    assert cli.main(["doctor"]) == 0
    out = capsys.readouterr().out

    assert "valid" in out
    assert "paper engine active" in out
    assert "Risk warning" in out


def test_doctor_flags_robinhood_without_pricing_inputs(capsys):
    cli.main(["--chains", "robinhood", "doctor"])
    assert "needs --v3-factory" in capsys.readouterr().out


def test_a_bad_config_is_rejected_before_anything_runs(capsys):
    assert cli.main(["--capital", "-5", "scan"]) == 1
    assert "Config error" in capsys.readouterr().err


def test_an_unreadable_config_file_is_reported(capsys):
    assert cli.main(["-c", "/nonexistent/desk.json", "plan"]) == 1
    assert "Could not read config" in capsys.readouterr().err


def test_an_unknown_chain_on_the_command_line_is_rejected(capsys):
    assert cli.main(["--chains", "dogechain", "scan"]) == 1
    assert "dogechain" in capsys.readouterr().err
