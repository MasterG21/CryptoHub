"""End-to-end smoke tests for the CLI with the network layer mocked out.

We can't reach robinhoodchain.blockscout.com from this environment, so these
exercise the CLI's wiring (argument parsing, client calls, ranking, output)
against fake responses shaped like Blockscout's v2 API, rather than the
real network.
"""
import json
from unittest.mock import patch

import pytest

from robinhood_meme_scan.blockscout import BlockscoutError, Holder, TokenInfo
from robinhood_meme_scan.cli import main


def make_token(symbol="DOGGY", name="Doggy", holder_count=120):
    return TokenInfo(
        address=f"0x{symbol}",
        name=name,
        symbol=symbol,
        decimals=18,
        total_supply=1_000_000,
        holder_count=holder_count,
        is_verified=True,
    )


@pytest.fixture
def mocked_chain():
    """Patches every network boundary the CLI touches."""
    with patch("robinhood_meme_scan.cli.BlockscoutClient") as MockClient, patch(
        "robinhood_meme_scan.screen.get_web3"
    ), patch("robinhood_meme_scan.screen.check_ownership") as mock_ownership:
        mock_ownership.return_value.supported = False
        instance = MockClient.return_value
        instance.get_smart_contract.return_value = {"source_code": "contract Doggy {}"}
        instance.get_top_holders.return_value = [
            Holder(address=f"0x{i:040x}", balance=5_000) for i in range(20)
        ]
        instance.get_creation_timestamp.return_value = None
        instance.get_deployer.return_value = None
        instance.get_deployed_tokens.return_value = []
        yield instance


def test_single_address_prints_detailed_report(mocked_chain, capsys):
    mocked_chain.get_token.return_value = make_token()

    assert main(["0xToken"]) == 0

    out = capsys.readouterr().out
    assert "DOGGY" in out
    assert "Score:" in out
    assert "Verified contract:" in out


def test_batch_prints_ranked_table_best_first(mocked_chain, capsys):
    clean = make_token(symbol="CLEAN")
    risky = make_token(symbol="RISKY", holder_count=3)

    def token_by_address(addr):
        return clean if addr == "0xClean" else risky

    mocked_chain.get_token.side_effect = token_by_address

    def contract_by_address(addr):
        # The risky token is unverified, which is the heaviest deduction.
        return {"source_code": "contract Clean {}"} if addr == "0xClean" else None

    mocked_chain.get_smart_contract.side_effect = contract_by_address

    assert main(["0xClean", "0xRisky"]) == 0

    out = capsys.readouterr().out
    assert "Ranked by rug-risk score" in out
    assert out.index("CLEAN") < out.index("RISKY"), "higher score must rank first"


def test_json_output_is_valid_and_sorted(mocked_chain, capsys):
    mocked_chain.get_token.side_effect = lambda addr: make_token(
        symbol="CLEAN" if addr == "0xClean" else "RISKY"
    )
    mocked_chain.get_smart_contract.side_effect = lambda addr: (
        {"source_code": "contract Clean {}"} if addr == "0xClean" else None
    )

    assert main(["0xClean", "0xRisky", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    scores = [r["score"] for r in payload["results"]]
    assert scores == sorted(scores, reverse=True)
    assert payload["results"][0]["symbol"] == "CLEAN"


def test_addresses_file_is_read_and_comments_ignored(mocked_chain, tmp_path, capsys):
    mocked_chain.get_token.return_value = make_token()
    listing = tmp_path / "addrs.txt"
    listing.write_text("# a comment\n0xAaa\n\n0xBbb  # trailing\n")

    assert main(["-f", str(listing), "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert len(payload["results"]) == 2


def test_duplicate_addresses_screened_once(mocked_chain, capsys):
    mocked_chain.get_token.return_value = make_token()

    assert main(["0xAaa", "0xAAA", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert len(payload["results"]) == 1


def test_one_bad_address_does_not_sink_the_batch(mocked_chain, capsys):
    def token_or_fail(addr):
        if addr == "0xBad":
            raise BlockscoutError("Token 0xBad not found on this explorer")
        return make_token()

    mocked_chain.get_token.side_effect = token_or_fail

    assert main(["0xGood", "0xBad", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert len(payload["results"]) == 1
    assert payload["failures"][0]["address"] == "0xBad"


def test_all_addresses_failing_exits_nonzero(mocked_chain):
    mocked_chain.get_token.side_effect = BlockscoutError("not found")

    assert main(["0xBad"]) == 1


def test_serial_deployer_is_flagged(mocked_chain, capsys):
    mocked_chain.get_token.return_value = make_token()
    mocked_chain.get_deployer.return_value = "0xdeployer"
    mocked_chain.get_deployed_tokens.return_value = [{"address": f"0x{i}"} for i in range(12)]

    assert main(["0xToken", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    result = payload["results"][0]
    assert result["deployer_token_count"] == 12
    assert any(f["label"] == "serial-deployer" for f in result["flags"])


def test_no_deployer_check_skips_the_lookup(mocked_chain, capsys):
    mocked_chain.get_token.return_value = make_token()

    assert main(["0xToken", "--no-deployer-check", "--json"]) == 0

    mocked_chain.get_deployer.assert_not_called()


def test_no_addresses_exits_nonzero(capsys):
    assert main([]) == 1
