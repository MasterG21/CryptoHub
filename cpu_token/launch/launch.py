"""One command that takes you from source to a verified, deployed token.

    python cpu_token/launch/launch.py            # dry run: plan only, broadcasts nothing
    python cpu_token/launch/launch.py --confirm  # actually deploy

Deliberately dry by default. Deployment is irreversible and costs real
money on mainnet, so the plan — network, chain id, addresses, supply
destination, gas estimate, balance after — is printed and checked first,
and nothing is signed until you pass --confirm.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from compile import (  # noqa: E402
    EVM_VERSION, OPTIMIZER_ENABLED, OPTIMIZER_RUNS, SOLC_VERSION, compile_contracts,
)
from config import ConfigError, LaunchConfig, load_config  # noqa: E402

BOLD, DIM, RED, YELLOW, GREEN, CYAN, RESET = (
    "\033[1m", "\033[2m", "\033[31m", "\033[33m", "\033[32m", "\033[36m", "\033[0m"
)


class LaunchError(RuntimeError):
    pass


def _h(text: str) -> None:
    print(f"\n{BOLD}{text}{RESET}")


def _row(label: str, value: str, colour: str = "") -> None:
    print(f"  {label:<25}{colour}{value}{RESET}")


# --------------------------------------------------------------------------
# preflight
# --------------------------------------------------------------------------

def preflight(w3, cfg: LaunchConfig, artifacts: dict, account) -> dict:
    """Check everything that can be checked before anything is signed.

    Every failure here is one that would otherwise surface as a burnt
    deployment: wrong chain, empty wallet, a reward token address with no
    contract behind it.
    """
    from web3 import Web3

    findings: list[str] = []

    if not w3.is_connected():
        raise LaunchError(f"Cannot reach the RPC at {cfg.rpc_url}")

    actual_chain = w3.eth.chain_id
    if actual_chain != cfg.chain_id:
        raise LaunchError(
            f"Chain id mismatch: NETWORK={cfg.network} expects {cfg.chain_id}, "
            f"but {cfg.rpc_url} reports {actual_chain}. Refusing to deploy — this is "
            "exactly how a token ends up on a chain you did not intend."
        )

    if not Web3.is_checksum_address(Web3.to_checksum_address(cfg.treasury)):
        raise LaunchError(f"TREASURY_ADDRESS {cfg.treasury} is not a valid address")

    balance = w3.eth.get_balance(account.address)
    # Check funds before estimating gas: an empty wallet makes estimation
    # itself fail, and "cannot afford txn gas" is a far less useful thing
    # to read than being told the wallet is empty.
    if balance == 0:
        raise LaunchError(
            f"Deployer {account.address} holds no BNB on {cfg.network_name}. "
            + ("Fund it from a BNB Chain testnet faucet and try again."
               if cfg.network == "testnet" else "Fund it and try again.")
        )

    # Estimate deployment cost from the actual bytecode, not a guess.
    gas_price = w3.eth.gas_price
    token = w3.eth.contract(
        abi=artifacts["ComputingPower"]["abi"], bytecode=artifacts["ComputingPower"]["bin"]
    )
    try:
        token_gas = token.constructor(
            Web3.to_checksum_address(cfg.treasury)
        ).estimate_gas({"from": account.address})
    except Exception as exc:
        raise LaunchError(f"Could not estimate gas for the token deployment: {exc}") from exc

    total_gas = token_gas
    dist_gas = None
    if cfg.reward_token:
        reward = Web3.to_checksum_address(cfg.reward_token)
        code = w3.eth.get_code(reward)
        if not code or len(code) == 0:
            raise LaunchError(
                f"REWARD_TOKEN_ADDRESS {reward} has no contract code on "
                f"{cfg.network_name}. Confirm the address on {cfg.explorer} first."
            )
        findings.append(
            "Reward token has contract code, but the launcher cannot verify it is the "
            "token you intended. Check it on the explorer."
        )
        # The distributor's own gas can only be estimated once the token
        # address exists, so use the bytecode length as a stand-in and add
        # generous headroom rather than under-quoting the total.
        dist_gas = 1_500_000
        total_gas += dist_gas

    cost = (total_gas * gas_price * 12) // 10  # 20% headroom
    if balance < cost:
        raise LaunchError(
            f"Deployer {account.address} holds {w3.from_wei(balance,'ether')} BNB but the "
            f"launch needs about {w3.from_wei(cost,'ether')} BNB including headroom."
        )

    return {
        "chain_id": actual_chain,
        "balance": balance,
        "gas_price": gas_price,
        "token_gas": token_gas,
        "distributor_gas": dist_gas,
        "estimated_cost": cost,
        "findings": findings,
    }


def print_plan(w3, cfg: LaunchConfig, checks: dict, account, confirm: bool) -> None:
    _h("Launch plan")
    warn = RED if cfg.network == "mainnet" else GREEN
    _row("Network", f"{cfg.network_name} (chain id {checks['chain_id']})", warn)
    _row("RPC", cfg.rpc_url)
    _row("Deployer", account.address)
    _row("Balance", f"{w3.from_wei(checks['balance'], 'ether')} BNB")
    _row("Gas price", f"{w3.from_wei(checks['gas_price'], 'gwei')} gwei")
    _row("Est. cost", f"~{w3.from_wei(checks['estimated_cost'], 'ether')} BNB")

    _h("Will deploy")
    _row("ComputingPower", "1,000,000,000 CPU, fixed supply")
    _row("  supply goes to", cfg.treasury, CYAN)
    if cfg.reward_token:
        _row("MerkleRewardDistributor", "epoch reward claims")
        _row("  reward token", cfg.reward_token, CYAN)
        _row("  owner", cfg.distributor_owner or account.address, CYAN)
    else:
        _row("MerkleRewardDistributor", "skipped (REWARD_TOKEN_ADDRESS unset)", DIM)

    if checks["findings"]:
        _h("Check these")
        for f in checks["findings"]:
            print(f"  {YELLOW}·{RESET} {f}")

    if not confirm:
        _h("Dry run — nothing was broadcast")
        print(f"  Re-run with {BOLD}--confirm{RESET} to deploy for real.")
        if cfg.network == "mainnet":
            print(f"  {YELLOW}This is mainnet. Rehearse on testnet first if you have not.{RESET}")


# --------------------------------------------------------------------------
# deployment
# --------------------------------------------------------------------------

def _deploy(w3, account, contract, args, gas_price, description: str):
    print(f"  deploying {description}...", flush=True)
    tx = contract.constructor(*args).build_transaction({
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
        "gasPrice": gas_price,
    })
    signed = account.sign_transaction(tx)
    raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
    tx_hash = w3.eth.send_raw_transaction(raw)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
    if receipt.status != 1:
        raise LaunchError(f"{description} deployment reverted: {tx_hash.hex()}")
    print(f"  {GREEN}✓{RESET} {description} at {BOLD}{receipt.contractAddress}{RESET}")
    return receipt


def run_launch(w3, cfg: LaunchConfig, artifacts: dict, account, confirm: bool,
               out_dir: str) -> dict:
    """Preflight, print the plan, and — only with confirm — deploy."""
    from web3 import Web3

    checks = preflight(w3, cfg, artifacts, account)
    print_plan(w3, cfg, checks, account, confirm)
    if not confirm:
        return {"dry_run": True, **{k: str(v) for k, v in checks.items() if k != "findings"}}

    _h("Deploying")
    gas_price = checks["gas_price"]
    treasury = Web3.to_checksum_address(cfg.treasury)

    token_c = w3.eth.contract(
        abi=artifacts["ComputingPower"]["abi"], bytecode=artifacts["ComputingPower"]["bin"]
    )
    token_receipt = _deploy(w3, account, token_c, [treasury], gas_price, "ComputingPower (CPU)")
    token_address = token_receipt.contractAddress

    result = {
        "dry_run": False,
        "network": cfg.network,
        "chain_id": cfg.chain_id,
        "deployed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "deployer": account.address,
        "compiler": {
            "version": SOLC_VERSION,
            "optimizer": OPTIMIZER_ENABLED,
            "runs": OPTIMIZER_RUNS,
            "evm_version": EVM_VERSION,
        },
        "contracts": {
            "ComputingPower": {
                "address": token_address,
                "tx": token_receipt.transactionHash.hex(),
                "constructor_args": [treasury],
            }
        },
    }

    if cfg.reward_token:
        owner = Web3.to_checksum_address(cfg.distributor_owner or account.address)
        reward = Web3.to_checksum_address(cfg.reward_token)
        dist_c = w3.eth.contract(
            abi=artifacts["MerkleRewardDistributor"]["abi"],
            bytecode=artifacts["MerkleRewardDistributor"]["bin"],
        )
        dist_receipt = _deploy(
            w3, account, dist_c, [reward, token_address, owner], gas_price,
            "MerkleRewardDistributor",
        )
        result["contracts"]["MerkleRewardDistributor"] = {
            "address": dist_receipt.contractAddress,
            "tx": dist_receipt.transactionHash.hex(),
            "constructor_args": [reward, token_address, owner],
        }

    # Sanity-check the deployed token rather than assuming it worked.
    token = w3.eth.contract(address=token_address, abi=artifacts["ComputingPower"]["abi"])
    supply = token.functions.totalSupply().call()
    held = token.functions.balanceOf(treasury).call()
    if supply != held or supply != 10**27:
        raise LaunchError(
            f"Post-deploy check failed: supply={supply}, treasury balance={held}"
        )
    print(f"  {GREEN}✓{RESET} verified on-chain: entire supply is at the treasury")

    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "deployment.json")
    with open(path, "w") as fh:
        json.dump(result, fh, indent=2)
    print(f"  {GREEN}✓{RESET} wrote {path}")
    return result


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Deploy Computing Power (CPU) to BNB Smart Chain.")
    p.add_argument("--confirm", action="store_true",
                   help="Actually broadcast. Without this the script only prints the plan.")
    p.add_argument("--env", default=".env", help="Path to the .env file (default: .env)")
    p.add_argument("--out", default="cpu_token/launch/out", help="Where to write deployment output")
    p.add_argument("--node-modules", default=None, help="Folder containing solc + OpenZeppelin")
    args = p.parse_args(argv)

    try:
        from eth_account import Account
        from web3 import Web3

        cfg = load_config(args.env)
        if not cfg.private_key:
            raise ConfigError("PRIVATE_KEY is not set in your .env")
        account = Account.from_key(cfg.private_key)

        print(f"{DIM}Compiling with solc {SOLC_VERSION} "
              f"(optimizer {'on' if OPTIMIZER_ENABLED else 'off'}, "
              f"{OPTIMIZER_RUNS} runs)...{RESET}")
        artifacts = compile_contracts(args.node_modules)["contracts"]

        w3 = Web3(Web3.HTTPProvider(cfg.rpc_url, request_kwargs={"timeout": 60}))
        result = run_launch(w3, cfg, artifacts, account, args.confirm, args.out)

        if not result["dry_run"]:
            from verify import write_verification_bundle
            bundle = write_verification_bundle(result, args.out, args.node_modules)
            _h("Next steps")
            print(f"  1. Verify the source on {cfg.explorer} — bundle written to {bundle}")
            print("  2. Add liquidity, then lock it. Nothing here does that for you.")
            print("  3. Screen your own token the way buyers will:")
            addr = result["contracts"]["ComputingPower"]["address"]
            print(f"       {DIM}python -m robinhood_meme_scan --chain bsc {addr}{RESET}")
        return 0

    except (ConfigError, LaunchError) as exc:
        print(f"\n{RED}{exc}{RESET}\n", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
