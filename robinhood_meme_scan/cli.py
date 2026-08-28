"""CLI: python -m robinhood_meme_scan <token_address> [options]"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from .analyzer import (
    build_report,
    score_age,
    score_holder_count,
    score_holders,
    score_liquidity,
    score_ownership,
    score_verification,
)
from .blockscout import BlockscoutClient, BlockscoutError, DEFAULT_EXPLORER_API
from .onchain import DEFAULT_RPC_URL, check_ownership, find_liquidity_pool, get_web3

RED = "\033[31m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
BOLD = "\033[1m"
RESET = "\033[0m"


def _color_for_score(score: int) -> str:
    if score >= 80:
        return GREEN
    if score >= 50:
        return YELLOW
    return RED


def _hours_since(iso_timestamp: str) -> float | None:
    try:
        ts = iso_timestamp.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        return delta.total_seconds() / 3600
    except (ValueError, AttributeError):
        return None


def run(args: argparse.Namespace) -> int:
    explorer = BlockscoutClient(base_url=args.explorer_api)

    try:
        token = explorer.get_token(args.token_address)
    except BlockscoutError as exc:
        print(f"{RED}Error: {exc}{RESET}", file=sys.stderr)
        return 1
    except Exception as exc:  # network/timeout/etc.
        print(f"{RED}Could not reach explorer API ({args.explorer_api}): {exc}{RESET}", file=sys.stderr)
        return 1

    report = build_report(token)

    contract = None
    try:
        contract = explorer.get_smart_contract(args.token_address)
    except Exception as exc:
        print(f"{YELLOW}Warning: verification lookup failed: {exc}{RESET}", file=sys.stderr)
    score_verification(report, contract)

    holders = []
    try:
        holders = explorer.get_top_holders(args.token_address)
    except Exception as exc:
        print(f"{YELLOW}Warning: holder lookup failed: {exc}{RESET}", file=sys.stderr)
    score_holder_count(report, token.holder_count)

    lp_address = None
    liquidity_checked = False
    liquidity_found = False
    token_balance = None

    if args.v3_factory and args.weth:
        liquidity_checked = True
        try:
            w3 = get_web3(args.rpc_url)
            pool = find_liquidity_pool(w3, args.token_address, args.v3_factory, args.weth)
            if pool:
                liquidity_found = True
                lp_address = pool.pool_address
                token_balance = pool.token_balance
        except Exception as exc:
            print(f"{YELLOW}Warning: liquidity check failed: {exc}{RESET}", file=sys.stderr)
            liquidity_checked = False
    score_liquidity(report, liquidity_checked, liquidity_found, token_balance)

    score_holders(report, holders, token.total_supply, lp_address)

    renounced = None
    try:
        w3 = get_web3(args.rpc_url)
        ownership = check_ownership(w3, args.token_address)
        if ownership.supported:
            renounced = ownership.renounced
    except Exception as exc:
        print(f"{YELLOW}Warning: ownership check failed: {exc}{RESET}", file=sys.stderr)
    score_ownership(report, renounced)

    hours_old = None
    try:
        created_at = explorer.get_creation_timestamp(args.token_address)
        if created_at:
            hours_old = _hours_since(created_at)
    except Exception as exc:
        print(f"{YELLOW}Warning: creation-time lookup failed: {exc}{RESET}", file=sys.stderr)
    score_age(report, hours_old)

    _print_report(report, args)
    return 0


def _print_report(report, args: argparse.Namespace) -> None:
    t = report.token
    color = _color_for_score(report.score)

    print(f"\n{BOLD}{t.name or '?'} ({t.symbol or '?'}){RESET}  {t.address}")
    print(f"{color}{BOLD}Score: {report.score}/100 — {report.verdict}{RESET}\n")

    print(f"Verified contract:   {t.is_verified if t.is_verified is not None else 'unknown'}")
    print(f"Holders on record:   {t.holder_count if t.holder_count is not None else 'unknown'}")
    if report.holder_top1_pct is not None:
        print(f"Top holder:          {report.holder_top1_pct:.1f}% of supply (excl. LP/burn)")
    if report.holder_top10_pct is not None:
        print(f"Top 10 holders:      {report.holder_top10_pct:.1f}% of supply (excl. LP/burn)")
    if report.ownership_renounced is not None:
        print(f"Ownership renounced: {report.ownership_renounced}")
    if report.contract_age_note:
        print(f"Age:                 {report.contract_age_note}")
    if report.liquidity_checked:
        print(f"Uniswap V3 pool:     {'found' if report.liquidity_found else 'not found'}")
    else:
        print("Uniswap V3 pool:     not checked (pass --v3-factory and --weth to enable)")

    if report.flags:
        print(f"\n{BOLD}Flags:{RESET}")
        for f in sorted(report.flags, key=lambda x: x.points):
            print(f"  [{f.points:+d}] {f.label}: {f.detail}")
    else:
        print(f"\n{GREEN}No flags raised.{RESET}")

    print(
        "\nHeuristic screen only — not a security audit and not investment "
        "advice. Verify anything material yourself on "
        f"{args.explorer_api.replace('/api/v2', '')} before acting on it.\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="robinhood-meme-scan",
        description="Heuristic rug-risk / health check for a Robinhood Chain ERC-20 meme coin.",
    )
    parser.add_argument("token_address", help="ERC-20 token contract address to analyze")
    parser.add_argument("--rpc-url", default=DEFAULT_RPC_URL, help="Robinhood Chain JSON-RPC endpoint")
    parser.add_argument(
        "--explorer-api", default=DEFAULT_EXPLORER_API, help="Blockscout v2 API base URL"
    )
    parser.add_argument(
        "--v3-factory",
        default=None,
        help="Uniswap V3 factory address on this chain (omit to skip the liquidity check)",
    )
    parser.add_argument(
        "--weth",
        default=None,
        help="Wrapped ETH token address on this chain (omit to skip the liquidity check)",
    )
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
