"""CLI: python -m robinhood_meme_scan [--chain bsc] <token_address> [...] [options]"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace

from .blockscout import BlockscoutClient, BlockscoutError
from .chains import CHAINS, DEFAULT_CHAIN, Chain, chain_choices, get_chain
from .screen import ScreenOptions, analyze_token

RED = "\033[31m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"

DISCLAIMER = (
    "Heuristic screen only — not a security audit and not investment advice. "
    "It flags whether a contract CAN be used against holders; it says nothing "
    "about whether the price will go up."
)


def _color_for_score(score: int) -> str:
    if score >= 80:
        return GREEN
    if score >= 50:
        return YELLOW
    return RED


def _read_addresses(args: argparse.Namespace) -> list[str]:
    addresses = list(args.token_addresses)
    if args.addresses_file:
        with open(args.addresses_file) as fh:
            for line in fh:
                line = line.split("#", 1)[0].strip()
                if line:
                    addresses.append(line)
    # Preserve order, drop duplicates.
    seen = set()
    unique = []
    for addr in addresses:
        key = addr.lower()
        if key not in seen:
            seen.add(key)
            unique.append(addr)
    return unique


def _resolve_chain(args: argparse.Namespace) -> Chain:
    """Chain preset with any explicitly passed flag taking precedence."""
    chain = get_chain(args.chain)
    overrides = {}
    if args.explorer_api:
        overrides["explorer_api"] = args.explorer_api
        overrides["explorer_url"] = args.explorer_api.replace("/api/v2", "")
    if args.rpc_url:
        overrides["rpc_url"] = args.rpc_url
    if args.v3_factory:
        overrides["v3_factory"] = args.v3_factory
    if args.quote_token:
        overrides["quote_token"] = args.quote_token
    if args.fee_tiers:
        overrides["v3_fee_tiers"] = tuple(
            int(t.strip()) for t in args.fee_tiers.split(",") if t.strip()
        )
    return replace(chain, **overrides) if overrides else chain


def _report_to_dict(report) -> dict:
    t = report.token
    return {
        "address": t.address,
        "name": t.name,
        "symbol": t.symbol,
        "score": report.score,
        "verdict": report.verdict,
        "is_verified": t.is_verified,
        "holder_count": t.holder_count,
        "holder_top1_pct": report.holder_top1_pct,
        "holder_top10_pct": report.holder_top10_pct,
        "ownership_renounced": report.ownership_renounced,
        "age": report.contract_age_note,
        "deployer": report.deployer,
        "deployer_token_count": report.deployer_token_count,
        "liquidity_checked": report.liquidity_checked,
        "liquidity_found": report.liquidity_found,
        "flags": [
            {"label": f.label, "points": f.points, "detail": f.detail} for f in report.flags
        ],
    }


def _print_single(report, chain: Chain) -> None:
    t = report.token
    color = _color_for_score(report.score)

    print(f"\n{BOLD}{t.name or '?'} ({t.symbol or '?'}){RESET}  {t.address}")
    print(f"{DIM}{chain.name}{RESET}")
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
    if report.deployer:
        count = report.deployer_token_count
        suffix = f" ({count} tokens launched)" if count is not None else ""
        print(f"Deployer:            {report.deployer}{suffix}")
    pool_label = f"{chain.dex_name} pool:"
    if report.liquidity_checked:
        print(f"{pool_label:<21}{'found' if report.liquidity_found else 'not found'}")
    else:
        print(f"{pool_label:<21}not checked (pass --v3-factory and --quote-token to enable)")

    if report.flags:
        print(f"\n{BOLD}Flags:{RESET}")
        for f in sorted(report.flags, key=lambda x: x.points):
            print(f"  [{f.points:+d}] {f.label}: {f.detail}")
    else:
        print(f"\n{GREEN}No flags raised.{RESET}")

    print(f"\n{DIM}{DISCLAIMER}{RESET}")
    print(f"{DIM}Verify anything material yourself on {chain.explorer_url}{RESET}\n")


def _print_table(results: list, failures: list[tuple[str, str]]) -> None:
    print(f"\n{BOLD}Ranked by rug-risk score (highest = fewest structural red flags){RESET}\n")

    header = f"{'SCORE':>5}  {'TOKEN':<22} {'TOP1%':>6} {'HOLDERS':>8} {'DEPLOYS':>7}  FLAGS"
    print(BOLD + header + RESET)
    print("-" * len(header))

    for report in results:
        t = report.token
        color = _color_for_score(report.score)
        # Pad on the visible text, then colorize — ANSI codes have no width
        # but str.format counts them, which would skew every column after this.
        plain_label = f"{t.symbol or '?'} {(t.name or '')[:12]}"
        padding = " " * max(0, 22 - len(plain_label))
        label = f"{t.symbol or '?'} {DIM}{(t.name or '')[:12]}{RESET}{padding}"
        top1 = f"{report.holder_top1_pct:.1f}" if report.holder_top1_pct is not None else "-"
        holders = str(t.holder_count) if t.holder_count is not None else "-"
        deploys = (
            str(report.deployer_token_count)
            if report.deployer_token_count is not None
            else "-"
        )
        top_flags = ", ".join(
            f.label for f in sorted(report.flags, key=lambda x: x.points)[:2]
        ) or "clean"
        print(
            f"{color}{report.score:>5}{RESET}  {label} {top1:>6} {holders:>8} "
            f"{deploys:>7}  {top_flags}"
        )

    if failures:
        print(f"\n{YELLOW}Could not screen:{RESET}")
        for addr, err in failures:
            print(f"  {addr}: {err}")

    print(f"\n{DIM}{DISCLAIMER}{RESET}\n")


def _print_chains() -> None:
    print(f"\n{BOLD}Built-in chain presets{RESET}\n")
    for key, chain in sorted(CHAINS.items()):
        default = "  (default)" if key == DEFAULT_CHAIN else ""
        print(f"{BOLD}--chain {key}{RESET}{default}  {chain.name}")
        print(f"  explorer  {chain.explorer_api}")
        print(f"  rpc       {chain.rpc_url}")
        if chain.liquidity_configured:
            tiers = ",".join(str(t) for t in chain.v3_fee_tiers)
            print(f"  liquidity {chain.dex_name} vs {chain.quote_symbol} at fee tiers {tiers}")
            print(f"  factory   {chain.v3_factory}")
            print(f"  {chain.quote_symbol:<9} {chain.quote_token}")
        else:
            print("  liquidity not configured — pass --v3-factory and --quote-token to enable")
        print()
    print(
        f"{DIM}Preset DEX addresses have not been confirmed against a live chain from this\n"
        f"repo's environment. A wrong one is reported as 'not checked', never as\n"
        f"'no liquidity' — but confirm on the explorer before relying on the result.{RESET}\n"
    )


def run(args: argparse.Namespace) -> int:
    addresses = _read_addresses(args)
    if not addresses:
        print(f"{RED}No token addresses given.{RESET}", file=sys.stderr)
        return 1

    chain = _resolve_chain(args)
    explorer = BlockscoutClient(base_url=chain.explorer_api)
    opts = ScreenOptions(
        rpc_url=chain.rpc_url,
        v3_factory=chain.v3_factory,
        quote_token=chain.quote_token,
        check_deployer=not args.no_deployer_check,
        fee_tiers=chain.v3_fee_tiers,
        dex_name=chain.dex_name,
        quote_symbol=chain.quote_symbol,
    )
    batch = len(addresses) > 1

    results = []
    failures: list[tuple[str, str]] = []

    for addr in addresses:
        def warn(msg: str, _addr=addr) -> None:
            if not args.json:
                print(f"{YELLOW}Warning [{_addr}]: {msg}{RESET}", file=sys.stderr)

        if batch and not args.json:
            print(f"{DIM}Screening {addr}...{RESET}", file=sys.stderr)
        try:
            results.append(analyze_token(explorer, addr, opts, warn=warn))
        except BlockscoutError as exc:
            failures.append((addr, str(exc)))
        except Exception as exc:
            failures.append((addr, f"could not reach explorer: {exc}"))

    if not results and failures:
        for addr, err in failures:
            print(f"{RED}Error [{addr}]: {err}{RESET}", file=sys.stderr)
        return 1

    results.sort(key=lambda r: r.score, reverse=True)

    if args.json:
        payload = {
            "results": [_report_to_dict(r) for r in results],
            "failures": [{"address": a, "error": e} for a, e in failures],
            "chain": chain.key,
            "disclaimer": DISCLAIMER,
        }
        print(json.dumps(payload, indent=2))
    elif batch:
        _print_table(results, failures)
    else:
        _print_single(results[0], chain)

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="robinhood-meme-scan",
        description=(
            "Heuristic rug-risk screen for ERC-20 / BEP-20 meme coins on Robinhood "
            "Chain and BNB Smart Chain. Pass one address for a detailed report, or "
            "several for a ranked table."
        ),
    )
    parser.add_argument(
        "token_addresses", nargs="*", help="One or more ERC-20 token contract addresses"
    )
    parser.add_argument(
        "-f",
        "--addresses-file",
        help="File with one token address per line ('#' comments allowed)",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of a table")
    parser.add_argument(
        "--chain",
        default=DEFAULT_CHAIN,
        choices=chain_choices(),
        metavar="{" + ",".join(sorted(CHAINS)) + "}",
        help=f"Which chain to screen on (default: {DEFAULT_CHAIN}). 'bnb'/'binance' also select bsc.",
    )
    parser.add_argument(
        "--list-chains", action="store_true", help="Print the built-in chain presets and exit"
    )
    parser.add_argument("--rpc-url", default=None, help="JSON-RPC endpoint (overrides the chain preset)")
    parser.add_argument(
        "--explorer-api", default=None, help="Blockscout v2 API base URL (overrides the chain preset)"
    )
    parser.add_argument(
        "--v3-factory",
        default=None,
        help="V3 factory address on this chain (overrides the chain preset)",
    )
    parser.add_argument(
        "--quote-token",
        "--weth",
        dest="quote_token",
        default=None,
        help="Quote token the pool is paired against — WETH/WBNB (overrides the chain preset)",
    )
    parser.add_argument(
        "--fee-tiers",
        default=None,
        help="Comma-separated V3 fee tiers to probe, e.g. 100,500,2500,10000 (overrides the preset)",
    )
    parser.add_argument(
        "--no-deployer-check",
        action="store_true",
        help="Skip the deployer / serial-launcher lookup (2 extra API calls per token)",
    )
    args = parser.parse_args(argv)
    if args.list_chains:
        _print_chains()
        return 0
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
