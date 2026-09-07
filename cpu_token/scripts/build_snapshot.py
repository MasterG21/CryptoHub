"""Build a reward epoch: snapshot CPU holders, split a pot, emit a Merkle root.

    python cpu_token/scripts/build_snapshot.py 0xCpuToken \
        --amount 1000000000000000000000 \
        --exclude 0xPancakePair --exclude 0xTreasury \
        --out epoch-001.json

Reads holder balances from the same Blockscout client the scanner in this
repo already uses, so there is one explorer client to keep working rather
than two. The output file carries the root to publish on-chain plus one
ready-to-submit proof per holder.

Excluding the right addresses is the part that actually matters. A
liquidity pool holds CPU on behalf of traders, not as a holder; paying it
would send rewards to the pool contract where nobody can claim them.
Burn addresses and the treasury are the same story. Pass every one of
them with --exclude; the script refuses to run without at least the pool,
unless you explicitly say there is none.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from merkle import build_claims  # noqa: E402
from robinhood_meme_scan.blockscout import BURN_ADDRESSES, BlockscoutClient  # noqa: E402
from robinhood_meme_scan.chains import get_chain  # noqa: E402


def fetch_holders(client: BlockscoutClient, token: str, page_limit: int) -> list[tuple[str, int]]:
    holders = client.get_top_holders(token, limit=page_limit)
    return [(h.address, h.balance) for h in holders]


def build_epoch(
    holders: list[tuple[str, int]],
    total_reward: int,
    excluded: set[str],
    min_payout: int,
) -> dict:
    eligible = [(a, b) for a, b in holders if a.lower() not in excluded and b > 0]
    if not eligible:
        raise SystemExit("No eligible holders after exclusions — nothing to distribute.")

    eligible_supply = sum(b for _, b in eligible)

    # Floor division throughout: the sum of payouts is therefore always
    # <= total_reward, never above it. The rounding dust stays in the
    # contract and is recoverable via sweepUnclaimed after the deadline.
    payouts = []
    for address, balance in eligible:
        amount = total_reward * balance // eligible_supply
        # Skip zero payouts as well as sub-threshold ones: a zero-value leaf
        # costs tree space and would have a holder pay gas to receive nothing.
        if amount >= min_payout and amount > 0:
            payouts.append((address, amount))

    if not payouts:
        raise SystemExit(
            f"Every payout landed below --min-payout ({min_payout}). "
            "Raise --amount or lower --min-payout."
        )

    payouts.sort(key=lambda p: p[1], reverse=True)
    root, claims = build_claims(payouts)
    allocated = sum(a for _, a in payouts)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "merkle_root": "0x" + root.hex(),
        "total_reward": str(total_reward),
        "allocated": str(allocated),
        "dust_remainder": str(total_reward - allocated),
        "eligible_supply": str(eligible_supply),
        "holder_count": len(payouts),
        "excluded": sorted(excluded),
        "claims": claims,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Build a Merkle reward epoch for CPU holders.")
    p.add_argument("token", help="CPU token contract address")
    p.add_argument("--amount", required=True, type=int,
                   help="Total reward to distribute, in the reward token's base units")
    p.add_argument("--exclude", action="append", default=[],
                   help="Address to exclude (repeatable): LP pair, treasury, distributor")
    p.add_argument("--no-pool", action="store_true",
                   help="Acknowledge that no liquidity pool needs excluding")
    p.add_argument("--min-payout", type=int, default=0,
                   help="Skip payouts below this many base units (saves gas on dust)")
    p.add_argument("--chain", default="bsc", help="Chain preset to read holders from")
    p.add_argument("--holders", type=int, default=1000, help="Max holders to fetch")
    p.add_argument("--out", default="epoch.json", help="Where to write the epoch file")
    args = p.parse_args(argv)

    if not args.exclude and not args.no_pool:
        p.error(
            "Refusing to build an epoch with no exclusions. The liquidity pool holds "
            "CPU on behalf of traders and would receive rewards nobody can claim. "
            "Pass --exclude <pair address>, or --no-pool if there really is no pool."
        )

    chain = get_chain(args.chain)
    client = BlockscoutClient(base_url=chain.explorer_api)

    print(f"Reading holders of {args.token} from {chain.name}...", file=sys.stderr)
    holders = fetch_holders(client, args.token, args.holders)
    if not holders:
        raise SystemExit("Explorer returned no holders — check the address and the chain.")
    print(f"  {len(holders)} holders returned", file=sys.stderr)

    excluded = {a.lower() for a in args.exclude} | {b.lower() for b in BURN_ADDRESSES}
    epoch = build_epoch(holders, args.amount, excluded, args.min_payout)

    with open(args.out, "w") as fh:
        json.dump(epoch, fh, indent=1)

    print(f"\n  merkle root   {epoch['merkle_root']}", file=sys.stderr)
    print(f"  holders paid  {epoch['holder_count']}", file=sys.stderr)
    print(f"  allocated     {epoch['allocated']}", file=sys.stderr)
    print(f"  dust left     {epoch['dust_remainder']}", file=sys.stderr)
    print(f"  written to    {args.out}\n", file=sys.stderr)
    print(
        "Check the root and the largest payouts before calling openEpoch(). "
        "A published root cannot be changed.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
