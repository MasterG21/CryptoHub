"""One command to run a reward epoch: snapshot, fund, publish.

    python cpu_token/launch/run_epoch.py --amount 1000000000000000000000 \
        --exclude 0xPancakePair
    # add --confirm to actually send the transactions

Dry by default, like the launcher. A published Merkle root cannot be
changed afterwards, so the split is printed for you to read before
anything is signed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from build_snapshot import build_epoch  # noqa: E402
from compile import compile_contracts  # noqa: E402
from config import ConfigError, load_config  # noqa: E402
from launch import BOLD, CYAN, DIM, GREEN, RED, RESET, YELLOW, LaunchError, _h, _row  # noqa: E402

from robinhood_meme_scan.blockscout import BURN_ADDRESSES, BlockscoutClient  # noqa: E402
from robinhood_meme_scan.chains import get_chain  # noqa: E402

MIN_CLAIM_WINDOW = 30 * 24 * 3600


def load_deployment(path: str) -> dict:
    if not os.path.exists(path):
        raise LaunchError(
            f"No deployment file at {path}. Run launch.py --confirm first, or pass "
            "--cpu and --distributor explicitly."
        )
    with open(path) as fh:
        return json.load(fh)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Open a funded reward epoch for CPU holders.")
    p.add_argument("--amount", required=True, type=int,
                   help="Total reward to distribute, in the reward token's base units")
    p.add_argument("--exclude", action="append", default=[],
                   help="Address to exclude (repeatable): LP pair, treasury, distributor")
    p.add_argument("--no-pool", action="store_true", help="Acknowledge there is no pool to exclude")
    p.add_argument("--claim-days", type=int, default=60, help="Claim window in days (min 30)")
    p.add_argument("--min-payout", type=int, default=0, help="Skip payouts below this many units")
    p.add_argument("--confirm", action="store_true", help="Actually broadcast")
    p.add_argument("--env", default=".env")
    p.add_argument("--deployment", default="cpu_token/launch/out/deployment.json")
    p.add_argument("--out", default="epoch.json")
    p.add_argument("--node-modules", default=None)
    args = p.parse_args(argv)

    try:
        from eth_account import Account
        from web3 import Web3

        if not args.exclude and not args.no_pool:
            raise LaunchError(
                "Refusing to build an epoch with no exclusions. The liquidity pool holds CPU "
                "for traders and would receive rewards nobody can claim. Pass --exclude "
                "<pair address>, or --no-pool if there really is no pool."
            )
        if args.claim_days * 24 * 3600 < MIN_CLAIM_WINDOW:
            raise LaunchError("--claim-days must be at least 30; the contract enforces this.")

        cfg = load_config(args.env)
        if not cfg.private_key:
            raise ConfigError("PRIVATE_KEY is not set in your .env")
        account = Account.from_key(cfg.private_key)

        deployment = load_deployment(args.deployment)
        cpu = deployment["contracts"]["ComputingPower"]["address"]
        if "MerkleRewardDistributor" not in deployment["contracts"]:
            raise LaunchError(
                "This deployment has no distributor. Set REWARD_TOKEN_ADDRESS in .env and "
                "deploy one before running an epoch."
            )
        distributor = deployment["contracts"]["MerkleRewardDistributor"]["address"]

        # --- snapshot ---
        chain = get_chain("bsc" if cfg.network == "mainnet" else "bsc")
        explorer = BlockscoutClient(base_url=chain.explorer_api)
        print(f"{DIM}Reading holders of {cpu}...{RESET}")
        holders = [(h.address, h.balance) for h in explorer.get_top_holders(cpu, limit=1000)]
        if not holders:
            raise LaunchError("Explorer returned no holders for this token.")

        excluded = ({a.lower() for a in args.exclude}
                    | {b.lower() for b in BURN_ADDRESSES}
                    | {distributor.lower()})
        epoch = build_epoch(holders, args.amount, excluded, args.min_payout)

        with open(args.out, "w") as fh:
            json.dump(epoch, fh, indent=1)

        _h("Epoch plan")
        _row("Network", cfg.network_name)
        _row("CPU token", cpu)
        _row("Distributor", distributor)
        _row("Reward token", cfg.reward_token or "(from deployment)", CYAN)
        _row("Holders paid", str(epoch["holder_count"]))
        _row("Total allocated", epoch["allocated"])
        _row("Dust remainder", epoch["dust_remainder"])
        _row("Claim window", f"{args.claim_days} days")
        _row("Merkle root", epoch["merkle_root"], CYAN)
        _row("Proofs written", args.out)

        print(f"\n  {BOLD}Largest payouts{RESET}")
        for c in epoch["claims"][:5]:
            print(f"    {c['account']}  {c['amount']}")

        if not args.confirm:
            _h("Dry run — nothing was broadcast")
            print(f"  Read the split above, then re-run with {BOLD}--confirm{RESET}.")
            print(f"  {YELLOW}A published root cannot be changed.{RESET}")
            return 0

        # --- broadcast ---
        artifacts = compile_contracts(args.node_modules)["contracts"]
        w3 = Web3(Web3.HTTPProvider(cfg.rpc_url, request_kwargs={"timeout": 60}))
        if w3.eth.chain_id != cfg.chain_id:
            raise LaunchError(
                f"Chain id mismatch: expected {cfg.chain_id}, RPC reports {w3.eth.chain_id}"
            )

        dist = w3.eth.contract(
            address=Web3.to_checksum_address(distributor),
            abi=artifacts["MerkleRewardDistributor"]["abi"],
        )
        reward_address = dist.functions.rewardToken().call()
        reward = w3.eth.contract(
            address=reward_address, abi=artifacts["MockERC20"]["abi"]  # standard ERC20 surface
        )

        allocated = int(epoch["allocated"])
        balance = reward.functions.balanceOf(account.address).call()
        if balance < allocated:
            raise LaunchError(
                f"{account.address} holds {balance} of the reward token but the epoch "
                f"needs {allocated}."
            )

        def send(fn, description):
            print(f"  {description}...", flush=True)
            tx = fn.build_transaction({
                "from": account.address,
                "nonce": w3.eth.get_transaction_count(account.address),
                "gasPrice": w3.eth.gas_price,
            })
            signed = account.sign_transaction(tx)
            raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
            receipt = w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(raw), timeout=300)
            if receipt.status != 1:
                raise LaunchError(f"{description} reverted")
            print(f"  {GREEN}✓{RESET} {description}")
            return receipt

        _h("Broadcasting")
        send(reward.functions.approve(dist.address, allocated), "approving the distributor")
        receipt = send(
            dist.functions.openEpoch(
                bytes.fromhex(epoch["merkle_root"][2:]), allocated, args.claim_days * 24 * 3600
            ),
            "opening the epoch",
        )
        epoch_id = dist.functions.epochCount().call() - 1
        print(f"\n  {GREEN}✓{RESET} epoch {BOLD}{epoch_id}{RESET} is live "
              f"({receipt.transactionHash.hex()})")
        print(f"  Publish {args.out} so holders can claim, and so anyone can rebuild")
        print(f"  the tree and check it against the on-chain root.")
        return 0

    except (ConfigError, LaunchError) as exc:
        print(f"\n{RED}{exc}{RESET}\n", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
