"""End-to-end smoke test for the CLI with the network layer mocked out.

We can't reach robinhoodchain.blockscout.com from this environment, so this
exercises the CLI's wiring (argument parsing, client calls, report printing)
against fake responses shaped like Blockscout's v2 API, rather than the real
network.
"""
from unittest.mock import patch

from robinhood_meme_scan.blockscout import Holder, TokenInfo
from robinhood_meme_scan.cli import main


def test_cli_runs_end_to_end_with_mocked_network(capsys):
    token = TokenInfo(
        address="0xToken",
        name="Doggy",
        symbol="DOGGY",
        decimals=18,
        total_supply=1_000_000,
        holder_count=120,
        is_verified=True,
    )
    holders = [Holder(address=f"0x{i:040x}", balance=5_000) for i in range(20)]

    with patch("robinhood_meme_scan.cli.BlockscoutClient") as MockClient:
        instance = MockClient.return_value
        instance.get_token.return_value = token
        instance.get_smart_contract.return_value = {"source_code": "contract Doggy {}"}
        instance.get_top_holders.return_value = holders
        instance.get_creation_timestamp.return_value = None

        with patch("robinhood_meme_scan.cli.get_web3") as mock_get_web3, \
             patch("robinhood_meme_scan.cli.check_ownership") as mock_check_ownership:
            mock_check_ownership.return_value.supported = False

            exit_code = main(["0xToken"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "DOGGY" in out
    assert "Score:" in out


def test_cli_handles_missing_token_gracefully(capsys):
    from robinhood_meme_scan.blockscout import BlockscoutError

    with patch("robinhood_meme_scan.cli.BlockscoutClient") as MockClient:
        instance = MockClient.return_value
        instance.get_token.side_effect = BlockscoutError("Token 0xBad not found on this explorer")

        exit_code = main(["0xBad"])

    assert exit_code == 1
