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
from robinhood_meme_scan.onchain import FactoryUnavailable, LiquidityPool

PLAIN_ABI = [
    {"type": "function", "name": n, "stateMutability": "view"}
    for n in ("name", "symbol", "decimals", "totalSupply", "balanceOf")
] + [
    {"type": "function", "name": n, "stateMutability": "nonpayable"}
    for n in ("transfer", "approve")
]


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
        instance.get_smart_contract.return_value = {"abi": PLAIN_ABI}
        instance.get_top_holders.return_value = [
            Holder(address=f"0x{i:040x}", balance=5_000) for i in range(20)
        ]
        instance.get_creation_timestamp.return_value = None
        instance.get_deployer.return_value = None
        instance.get_deployed_tokens.return_value = []
        # A real dict, not a MagicMock: .get("is_contract") on a MagicMock is
        # truthy, which would make every deployer look like a launchpad factory.
        instance.get_address_info.return_value = {"is_contract": False}
        # Exposed so chain-selection tests can assert which explorer the CLI
        # pointed the client at, without changing what this fixture yields.
        instance.client_class = MockClient
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
        return {"abi": PLAIN_ABI} if addr == "0xClean" else None

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
        {"abi": PLAIN_ABI} if addr == "0xClean" else None
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


def test_factory_deployer_not_flagged_via_cli(mocked_chain, capsys):
    """Launchpad tokens are all created by the platform factory — that must
    not penalise every token on the platform."""
    mocked_chain.get_token.return_value = make_token()
    mocked_chain.get_deployer.return_value = "0xfactory"
    mocked_chain.get_address_info.return_value = {"is_contract": True}
    mocked_chain.get_deployed_tokens.return_value = [{} for _ in range(50)]

    assert main(["0xToken", "--json"]) == 0

    result = json.loads(capsys.readouterr().out)["results"][0]
    assert not any("deployer" in f["label"] for f in result["flags"])


# --- chain selection -------------------------------------------------------


@pytest.fixture
def mocked_liquidity():
    """Patches the liquidity probe so chain tests don't touch web3."""
    with patch("robinhood_meme_scan.screen.find_liquidity_pool") as find_pool:
        find_pool.return_value = None
        yield find_pool


def test_chain_bsc_points_at_the_bnb_explorer(mocked_chain, mocked_liquidity, capsys):
    mocked_chain.get_token.return_value = make_token()

    assert main(["0xToken", "--chain", "bsc", "--json"]) == 0

    base_url = mocked_chain.client_class.call_args.kwargs["base_url"]
    assert "bnb.blockscout.com" in base_url
    assert json.loads(capsys.readouterr().out)["chain"] == "bsc"


def test_bnb_alias_selects_the_same_chain(mocked_chain, mocked_liquidity, capsys):
    mocked_chain.get_token.return_value = make_token()

    assert main(["0xToken", "--chain", "bnb", "--json"]) == 0

    assert json.loads(capsys.readouterr().out)["chain"] == "bsc"


def test_bsc_probes_pancakeswap_fee_tiers(mocked_chain, mocked_liquidity):
    mocked_chain.get_token.return_value = make_token()

    assert main(["0xToken", "--chain", "bsc", "--json"]) == 0

    fee_tiers = mocked_liquidity.call_args.args[-1]
    assert tuple(fee_tiers) == (100, 500, 2500, 10000)


def test_default_chain_still_skips_the_liquidity_check(mocked_chain, mocked_liquidity, capsys):
    """Robinhood Chain has no confirmed factory address, so nothing is probed
    and nothing is deducted."""
    mocked_chain.get_token.return_value = make_token()

    assert main(["0xToken", "--json"]) == 0

    mocked_liquidity.assert_not_called()
    result = json.loads(capsys.readouterr().out)["results"][0]
    assert result["liquidity_checked"] is False


def test_misconfigured_factory_reads_as_unknown_not_as_no_liquidity(
    mocked_chain, mocked_liquidity, capsys
):
    """The important one: a bad factory address must never cost a token
    points, because that would be the tool's fault, not the token's."""
    mocked_chain.get_token.return_value = make_token()
    mocked_liquidity.side_effect = FactoryUnavailable("no contract code at V3 factory")

    assert main(["0xToken", "--chain", "bsc", "--json"]) == 0

    result = json.loads(capsys.readouterr().out)["results"][0]
    assert result["liquidity_checked"] is False
    assert not any(f["label"] == "no-liquidity-pool" for f in result["flags"])


def test_genuine_absence_of_a_pool_is_still_flagged(mocked_chain, mocked_liquidity, capsys):
    mocked_chain.get_token.return_value = make_token()
    mocked_liquidity.return_value = None  # factory answered: no pool

    assert main(["0xToken", "--chain", "bsc", "--json"]) == 0

    result = json.loads(capsys.readouterr().out)["results"][0]
    assert result["liquidity_checked"] is True
    flag = next(f for f in result["flags"] if f["label"] == "no-liquidity-pool")
    assert "PancakeSwap V3" in flag["detail"]
    assert "WBNB" in flag["detail"]


def test_single_report_names_the_chain_and_dex(mocked_chain, mocked_liquidity, capsys):
    mocked_chain.get_token.return_value = make_token()
    mocked_liquidity.return_value = LiquidityPool(
        fee_tier=2500, pool_address="0xpool", token_balance=1_000
    )

    assert main(["0xToken", "--chain", "bsc"]) == 0

    out = capsys.readouterr().out
    assert "BNB Smart Chain" in out
    assert "PancakeSwap V3 pool:" in out
    assert "found" in out
    assert "bscscan.com" in out


def test_explicit_flags_override_the_chain_preset(mocked_chain, mocked_liquidity):
    mocked_chain.get_token.return_value = make_token()

    assert (
        main([
            "0xToken",
            "--chain", "bsc",
            "--explorer-api", "https://my-explorer.example/api/v2",
            "--fee-tiers", "500,3000",
            "--json",
        ])
        == 0
    )

    assert (
        mocked_chain.client_class.call_args.kwargs["base_url"]
        == "https://my-explorer.example/api/v2"
    )
    assert tuple(mocked_liquidity.call_args.args[-1]) == (500, 3000)


def test_list_chains_exits_zero_without_addresses(capsys):
    assert main(["--list-chains"]) == 0

    out = capsys.readouterr().out
    assert "BNB Smart Chain" in out
    assert "Robinhood Chain" in out
