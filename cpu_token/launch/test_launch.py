"""Exercises the launcher against an in-process EVM.

The point is to prove the deploy path works and, more importantly, that
the guards actually stop a bad launch: wrong chain, unfunded wallet, a
reward token address with nothing behind it.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from eth_account import Account  # noqa: E402
from web3 import EthereumTesterProvider, Web3  # noqa: E402

import config as config_mod  # noqa: E402
from compile import compile_contracts  # noqa: E402
from config import LaunchConfig, load_config  # noqa: E402
from launch import LaunchError, run_launch  # noqa: E402
from verify import encode_constructor_args, write_verification_bundle  # noqa: E402

PASSED, FAILED = [], []


def check(name, fn):
    try:
        fn()
        PASSED.append(name)
        print(f"  PASS  {name}")
    except Exception as exc:
        FAILED.append((name, exc))
        print(f"  FAIL  {name}: {exc}")


def expect_error(fn, needle):
    try:
        fn()
    except LaunchError as exc:
        assert needle.lower() in str(exc).lower(), f"wrong error: {exc}"
        return
    raise AssertionError(f"expected a LaunchError mentioning {needle!r}")


def main():
    artifacts = compile_contracts(os.environ.get("NODE_MODULES"))["contracts"]

    w3 = Web3(EthereumTesterProvider())
    tester = w3.provider.ethereum_tester
    chain_id = w3.eth.chain_id

    # Register the tester's chain id so config validation can target it.
    config_mod.NETWORKS["local"] = {
        "chain_id": chain_id, "name": "Local test chain", "explorer": "http://localhost",
    }

    funded = w3.eth.accounts[0]
    key = "0x" + "11" * 32
    account = Account.from_key(key)
    w3.eth.send_transaction({
        "from": funded, "to": account.address, "value": w3.to_wei(10, "ether"),
    })
    treasury = w3.eth.accounts[3]

    def cfg(**kw):
        base = dict(network="local", rpc_url="http://local", treasury=treasury, _private_key=key)
        base.update(kw)
        return LaunchConfig(**base)

    print("\nGuards (nothing should be broadcast):")
    check("chain id mismatch is refused", lambda: expect_error(
        lambda: run_launch(w3, cfg(network="mainnet"), artifacts, account, True, "/tmp/x"),
        "chain id mismatch"))

    poor = Account.from_key("0x" + "22" * 32)
    check("unfunded deployer is refused with a clear message", lambda: expect_error(
        lambda: run_launch(w3, cfg(), artifacts, poor, True, "/tmp/x"), "holds no BNB"))

    check("reward token with no code is refused", lambda: expect_error(
        lambda: run_launch(w3, cfg(reward_token="0x" + "de" * 20), artifacts, account,
                           True, "/tmp/x"),
        "no contract code"))

    print("\nDry run:")
    with tempfile.TemporaryDirectory() as td:
        res = run_launch(w3, cfg(), artifacts, account, False, td)
        check("dry run reports itself", lambda: _assert(res["dry_run"] is True))
        check("dry run writes nothing", lambda: _assert(not os.listdir(td)))
        check("dry run leaves the chain untouched",
              lambda: _assert(w3.eth.get_transaction_count(account.address) == 0))

    print("\nReal deployment:")
    out = tempfile.mkdtemp()
    result = run_launch(w3, cfg(), artifacts, account, True, out)
    token_addr = result["contracts"]["ComputingPower"]["address"]
    token = w3.eth.contract(address=token_addr, abi=artifacts["ComputingPower"]["abi"])

    check("deployment.json written",
          lambda: _assert(os.path.exists(os.path.join(out, "deployment.json"))))
    check("supply is 1e9 CPU", lambda: _eq(token.functions.totalSupply().call(), 10**27))
    check("entire supply is at the treasury",
          lambda: _eq(token.functions.balanceOf(treasury).call(), 10**27))
    check("deployer holds no CPU",
          lambda: _eq(token.functions.balanceOf(account.address).call(), 0))
    check("compiler settings recorded for verification",
          lambda: _eq(result["compiler"]["runs"], 200))

    print("\nDeployment with a reward distributor:")
    mock = w3.eth.contract(abi=artifacts["MockERC20"]["abi"], bytecode=artifacts["MockERC20"]["bin"])
    tx = mock.constructor("Reward", "RWD", 10**24).transact({"from": funded})
    reward_addr = w3.eth.wait_for_transaction_receipt(tx).contractAddress

    out2 = tempfile.mkdtemp()
    res2 = run_launch(w3, cfg(reward_token=reward_addr), artifacts, account, True, out2)
    dist = res2["contracts"]["MerkleRewardDistributor"]
    dist_c = w3.eth.contract(address=dist["address"], abi=artifacts["MerkleRewardDistributor"]["abi"])

    check("distributor points at the reward token",
          lambda: _eq(dist_c.functions.rewardToken().call(), Web3.to_checksum_address(reward_addr)))
    check("distributor points at the CPU token just deployed",
          lambda: _eq(dist_c.functions.holdingsToken().call(),
                      res2["contracts"]["ComputingPower"]["address"]))
    check("distributor owner defaults to the deployer",
          lambda: _eq(dist_c.functions.owner().call(), account.address))

    print("\nVerification bundle:")
    bundle = write_verification_bundle(res2, out2, os.environ.get("NODE_MODULES"))
    check("standard-json input written per contract", lambda: _assert(all(
        os.path.exists(os.path.join(bundle, n, "standard-input.json"))
        for n in res2["contracts"])))

    def args_decode():
        from eth_abi import decode
        with open(os.path.join(bundle, "ComputingPower", "constructor-args.txt")) as fh:
            raw = fh.read()
        (decoded,) = decode(["address"], bytes.fromhex(raw))
        _eq(Web3.to_checksum_address(decoded), Web3.to_checksum_address(treasury))
    check("constructor args round-trip to the treasury address", args_decode)

    def sources_complete():
        with open(os.path.join(bundle, "ComputingPower", "standard-input.json")) as fh:
            si = json.load(fh)
        # Verification fails if any import is missing from the bundle.
        _assert("ComputingPower.sol" in si["sources"])
        _assert(si["settings"]["optimizer"]["runs"] == 200)
    check("bundle carries sources and matching optimizer settings", sources_complete)

    print("\nConfig validation:")
    def bad_key():
        try:
            load_config("/nonexistent", overrides={
                "RPC_URL": "http://x", "TREASURY_ADDRESS": "0x1", "PRIVATE_KEY": "abc",
                "NETWORK": "testnet"})
        except config_mod.ConfigError as e:
            assert "32-byte hex" in str(e)
            return
        raise AssertionError("short private key was accepted")
    check("malformed private key is rejected", bad_key)

    def no_treasury():
        try:
            load_config("/nonexistent", overrides={
                "RPC_URL": "http://x", "TREASURY_ADDRESS": "", "NETWORK": "testnet"})
        except config_mod.ConfigError as e:
            assert "TREASURY_ADDRESS" in str(e)
            return
        raise AssertionError("missing treasury was accepted")
    check("missing treasury is rejected", no_treasury)

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


def _eq(a, b):
    assert a == b, f"{a!r} != {b!r}"


def _assert(c):
    assert c


if __name__ == "__main__":
    raise SystemExit(main())
