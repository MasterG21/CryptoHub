"""CLI: python -m trading_desk <command> [options]

Commands
    plan      What $100 -> $1,000,000 requires, in numbers. Start here.
    scan      One pass of discovery, safety screening and scoring. No trading.
    run       The autonomous loop. Paper by default.
    serve     Run the desk behind a local web dashboard.
    status    Portfolio, open positions and realised performance.
    simulate  Monte-Carlo the strategy forward under an assumed distribution.
    panic     Flatten every open position now.
    doctor    Validate configuration and report what live trading still needs.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Optional

from robinhood_meme_scan.blockscout import DEFAULT_EXPLORER_API, BlockscoutClient
from robinhood_meme_scan.onchain import DEFAULT_RPC_URL
from robinhood_meme_scan.screen import ScreenOptions

from . import growth as growth_mod
from .config import DeskConfig, load_config, validate_config
from .desk import TradingDesk
from .execution.live import LiveExecutor
from .execution.paper import PaperExecutor
from .execution.signers import (
    EVM_KEY_ENV,
    SOLANA_KEY_ENV,
    EvmSigner,
    MultiChainSigner,
    SignerLimits,
)
from .journal import Journal
from .marketdata.base import MultiChainFeed
from .marketdata.dexscreener import DexScreenerFeed
from .marketdata.history import PriceHistory
from .marketdata.robinhood import RobinhoodFeed
from .models import Chain
from .safety import SafetyGate, make_robinhood_deep_screen
from .strategy import evaluate_entry

RED = "\033[31m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
CYAN = "\033[36m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"

DISCLAIMER = (
    "Autonomous memecoin trading is a way to lose money quickly and "
    "automatically. This is software, not investment advice, and nothing here "
    "predicts returns. Paper mode is the default; run it long enough to see "
    "your own numbers before considering anything else."
)


# --------------------------------------------------------------------- wiring


def build_feed(cfg: DeskConfig, args: argparse.Namespace, history: PriceHistory) -> MultiChainFeed:
    feeds = []
    for chain in cfg.chains:
        if chain in (Chain.SOLANA, Chain.BNB):
            feeds.append(DexScreenerFeed(chain))
        elif chain is Chain.ROBINHOOD:
            feeds.append(
                RobinhoodFeed(
                    rpc_url=args.rpc_url,
                    explorer_api=args.explorer_api,
                    v3_factory=args.v3_factory,
                    weth=args.weth,
                    native_usd_price=args.native_usd,
                    history=history,
                )
            )
    return MultiChainFeed(feeds)


def build_safety_gate(cfg: DeskConfig, args: argparse.Namespace, history: PriceHistory) -> SafetyGate:
    deep_screen = None
    if Chain.ROBINHOOD in cfg.chains and cfg.safety.require_robinhood_screen:
        deep_screen = make_robinhood_deep_screen(
            BlockscoutClient(base_url=args.explorer_api),
            ScreenOptions(
                rpc_url=args.rpc_url,
                v3_factory=args.v3_factory,
                weth=args.weth,
                check_deployer=True,
            ),
        )
    return SafetyGate(cfg.safety, deep_screen=deep_screen, history=history)


def build_signer(cfg: DeskConfig, args: argparse.Namespace):
    """Assemble a signer from whichever chain keys are present in the env.

    Returns None when no key is set, which leaves live mode unarmed and the
    executor refusing every order — the correct outcome for a misconfigured
    live run, and the reason this never falls back to paper silently.
    """
    limits = SignerLimits(
        # Arming is a separate, explicit flag. Without it the signer builds and
        # simulates real transactions but broadcasts nothing.
        dry_run=not getattr(args, "arm", False),
        max_order_usd=getattr(args, "max_order_usd", 25.0),
        simulate_before_send=True,
        max_slippage_pct=cfg.execution.max_slippage_pct,
    )
    signers = {}
    if os.environ.get(SOLANA_KEY_ENV):
        # Imported lazily: solders is an optional dependency and only Solana
        # traders need it installed.
        from .execution.signers import SolanaSigner

        signers[Chain.SOLANA] = SolanaSigner(
            rpc_url=args.solana_rpc, limits=limits
        )
    if os.environ.get(EVM_KEY_ENV):
        signers[Chain.BNB] = EvmSigner(rpc_url=args.bnb_rpc, limits=limits)
    return MultiChainSigner(signers) if signers else None


def build_desk(cfg: DeskConfig, args: argparse.Namespace) -> TradingDesk:
    history = PriceHistory()
    journal = Journal(cfg.journal_path) if not args.no_journal else None
    if cfg.execution.mode == "live":
        executor = LiveExecutor(cfg, signer=build_signer(cfg, args))
    else:
        executor = PaperExecutor(cfg, failure_rate=args.failure_rate)
    return TradingDesk(
        config=cfg,
        feed=build_feed(cfg, args, history),
        executor=executor,
        journal=journal,
        safety_gate=build_safety_gate(cfg, args, history),
        history=history,
    )


# -------------------------------------------------------------------- helpers


def _money(value: float) -> str:
    return f"${value:,.2f}"


def _pct(value: Optional[float]) -> str:
    return "-" if value is None else f"{value * 100:+.1f}%"


def _risk_banner(cfg: DeskConfig) -> list[str]:
    """The one warning worth printing before every run.

    Sizing above the growth-optimal fraction is not a matter of appetite: it
    lowers expected growth *and* raises the chance of ruin at the same time.
    If that is the case here, say so every single time.
    """
    dist = growth_mod.DEFAULT_DISTRIBUTION
    math_ = growth_mod.GrowthMath(
        cfg.starting_capital_usd, cfg.target_usd, cfg.risk.risk_per_trade_pct, dist
    )
    if not math_.overbet:
        return []
    viable = growth_mod.minimum_viable_equity(
        dist, cfg.risk.min_position_usd, cfg.strategy.stop_loss_pct
    )
    lines = [
        f"{YELLOW}Risk warning:{RESET} risking "
        f"{cfg.risk.risk_per_trade_pct * 100:.1f}% per trade is above the "
        f"{math_.optimal_fraction * 100:.2f}% that maximises growth under the "
        "default assumed distribution."
    ]
    if math_.log_growth <= 0:
        lines.append(
            f"  At this size the account's expected log growth is "
            f"{math_.log_growth:+.5f} per trade — negative means it trends to zero."
        )
    lines.append(
        f"  Betting growth-optimally needs about {_money(viable)} of equity, "
        f"because a {_money(cfg.risk.min_position_usd)} minimum position cannot "
        "risk less than that."
    )
    lines.append(f"  {DIM}Run `python -m trading_desk plan` for the full picture.{RESET}")
    return lines


# ------------------------------------------------------------------- commands


def cmd_plan(cfg: DeskConfig, args: argparse.Namespace) -> int:
    dist = growth_mod.DEFAULT_DISTRIBUTION
    fraction = cfg.risk.risk_per_trade_pct
    math_ = growth_mod.GrowthMath(cfg.starting_capital_usd, cfg.target_usd, fraction, dist)

    print(f"\n{BOLD}The target{RESET}")
    print(f"  {_money(cfg.starting_capital_usd)} -> {_money(cfg.target_usd)} "
          f"is a {math_.required_multiple:,.0f}x.")
    print("  Broken into equal-ratio rungs, every one of these is the same amount of work:")
    for low, high in growth_mod.milestone_ladder(cfg.starting_capital_usd, cfg.target_usd):
        print(f"    {_money(low):>12} -> {_money(high):<12} {DIM}(x{high / low:.2f}){RESET}")

    print(f"\n{BOLD}The assumed edge{RESET} {DIM}(assumption, not measurement){RESET}")
    for outcome in dist.outcomes:
        print(f"  {outcome.probability * 100:5.1f}%  {outcome.r_multiple:+6.2f}R  "
              f"{DIM}{outcome.label}{RESET}")
    print(f"  {BOLD}Expectancy{RESET}    {dist.expectancy_r:+.3f}R per trade, "
          f"win rate {dist.win_rate * 100:.0f}%")

    print(f"\n{BOLD}Sizing{RESET}")
    print(f"  Configured risk per trade   {fraction * 100:.2f}%")
    print(f"  Growth-optimal (full Kelly) {math_.optimal_fraction * 100:.2f}%")
    print(f"  Log growth per trade        {math_.log_growth:+.5f}")
    trades = math_.trades_required
    if trades is None:
        print(f"  {RED}At this size the account compounds downward: the target is "
              f"not reachable, it is unreachable by construction.{RESET}")
    else:
        print(f"  Trades to target            {trades:,.0f}")
        days = math_.days_required(args.trades_per_day)
        if days:
            print(f"  At {args.trades_per_day:.0f} trades/day       {days:,.0f} days "
                  f"({days / 365:.1f} years)")

    viable = growth_mod.minimum_viable_equity(
        dist, cfg.risk.min_position_usd, cfg.strategy.stop_loss_pct
    )
    print(f"\n{BOLD}The small-account problem{RESET}")
    print(f"  A {_money(cfg.risk.min_position_usd)} minimum position across a "
          f"{cfg.strategy.stop_loss_pct * 100:.0f}% stop risks "
          f"{_money(cfg.risk.min_position_usd * cfg.strategy.stop_loss_pct)}.")
    print(f"  To make that a {math_.optimal_fraction * 100:.2f}% bet you need "
          f"{_money(viable)} of equity.")
    if cfg.starting_capital_usd < viable:
        print(f"  {RED}Starting at {_money(cfg.starting_capital_usd)}, the smallest trade "
              f"the desk can place is already an overbet.{RESET}")
        print(f"  {DIM}That is a property of the account size, not of the strategy or "
              f"the config — no setting fixes it.{RESET}")

    stall = growth_mod.stall_equity(
        fraction, cfg.risk.min_position_usd, cfg.strategy.stop_loss_pct
    )
    room = 1 - stall / cfg.starting_capital_usd if cfg.starting_capital_usd else 0.0
    print(f"  Below {_money(stall)} of equity no valid trade exists at all: "
          f"this account has {RED}{room * 100:.0f}% of drawdown{RESET}")
    print("  before it stops being able to trade, whatever the equity floor says.")

    print(f"\n{BOLD}Everything depends on the tail{RESET}")
    print(f"  {'biggest winner':>14}  {'expectancy':>10}  {'kelly':>7}  "
          f"{'growth @ ' + f'{fraction * 100:.0f}%':>12}")
    for row in growth_mod.tail_sensitivity(dist, fraction):
        colour = GREEN if row["survivable"] else RED
        print(f"  {row['tail_r']:>13.0f}R  {row['expectancy_r']:>+9.3f}R  "
              f"{row['kelly_fraction'] * 100:>6.2f}%  "
              f"{colour}{row['log_growth']:>+12.5f}{RESET}")
    print(f"  {DIM}One unknowable number decides the outcome. That is the honest "
          f"summary of this trade.{RESET}")

    result = growth_mod.simulate(
        start_usd=cfg.starting_capital_usd,
        target_usd=cfg.target_usd,
        fraction=fraction,
        trades=args.trades,
        runs=args.runs,
        ruin_floor_usd=cfg.risk.equity_floor_usd,
        min_position_usd=cfg.risk.min_position_usd,
        stop_loss_pct=cfg.strategy.stop_loss_pct,
    )
    _print_simulation(result, cfg)
    print(f"\n{DIM}{DISCLAIMER}{RESET}\n")
    return 0


def _print_simulation(result: growth_mod.SimulationResult, cfg: DeskConfig) -> None:
    print(f"\n{BOLD}Monte Carlo{RESET} {DIM}({result.runs:,} runs of up to "
          f"{result.trades_per_run:,} trades){RESET}")
    print(f"  Reached {_money(cfg.target_usd):<12}  {GREEN if result.p_target > 0.01 else RED}"
          f"{result.p_target * 100:.2f}%{RESET}")
    print(f"  Ruined (below {_money(cfg.risk.equity_floor_usd)})  "
          f"{RED}{result.p_ruin * 100:.2f}%{RESET}")
    print(f"  Stalled (too small to trade)  {RED}{result.p_stalled * 100:.2f}%{RESET} "
          f"{DIM}— still has money, cannot place the minimum position{RESET}")
    print(f"  {BOLD}Dead either way{RESET}          {RED}{result.p_dead * 100:.2f}%{RESET}")
    print(f"  Median ending equity     {_money(result.median_equity)}")
    print(f"  Mean ending equity       {_money(result.mean_equity)} "
          f"{DIM}(dragged up by the runs that got lucky){RESET}")
    print(f"  5th / 95th percentile    {_money(result.percentile(5))} / "
          f"{_money(result.percentile(95))}")
    if result.median_trades_to_target:
        print(f"  Median trades to target  {result.median_trades_to_target:,}")
    if result.mean_equity > result.median_equity * 2:
        print(f"  {DIM}Mean far above median is the signature of this asset class: "
              f"a few runs carry the average while most accounts lose.{RESET}")


def cmd_simulate(cfg: DeskConfig, args: argparse.Namespace) -> int:
    result = growth_mod.simulate(
        start_usd=cfg.starting_capital_usd,
        target_usd=cfg.target_usd,
        fraction=args.risk if args.risk is not None else cfg.risk.risk_per_trade_pct,
        trades=args.trades,
        runs=args.runs,
        ruin_floor_usd=cfg.risk.equity_floor_usd,
        min_position_usd=cfg.risk.min_position_usd,
        stop_loss_pct=cfg.strategy.stop_loss_pct,
        seed=args.seed,
    )
    if args.json:
        print(json.dumps(
            {
                "runs": result.runs,
                "p_target": result.p_target,
                "p_ruin": result.p_ruin,
                "p_stalled": result.p_stalled,
                "p_dead": result.p_dead,
                "median_equity": result.median_equity,
                "mean_equity": result.mean_equity,
                "p05": result.percentile(5),
                "p95": result.percentile(95),
                "median_trades_to_target": result.median_trades_to_target,
            },
            indent=2,
        ))
        return 0
    _print_simulation(result, cfg)
    print(f"\n{DIM}{DISCLAIMER}{RESET}\n")
    return 0


def cmd_scan(cfg: DeskConfig, args: argparse.Namespace) -> int:
    history = PriceHistory()
    feed = build_feed(cfg, args, history)
    gate = build_safety_gate(cfg, args, history)

    pairs = feed.discover(limit_per_chain=cfg.max_candidates_per_chain)
    for chain, error in feed.errors:
        print(f"{YELLOW}Warning [{chain.label}]: {error}{RESET}", file=sys.stderr)
    if not pairs:
        print(f"{RED}No pairs returned by any feed.{RESET}", file=sys.stderr)
        return 1

    rows = []
    rejected = 0
    for pair in pairs:
        verdict = gate.evaluate(pair)
        if not verdict.passed:
            rejected += 1
            if not args.all:
                continue
        rows.append(evaluate_entry(pair, verdict, cfg.strategy))
    rows.sort(key=lambda c: (c.tradeable, c.score), reverse=True)

    if args.json:
        print(json.dumps(
            {
                "scanned": len(pairs),
                "safety_rejected": rejected,
                "candidates": [
                    {
                        "chain": c.pair.chain.value,
                        "symbol": c.pair.base_symbol,
                        "address": c.pair.base_address,
                        "price_usd": c.pair.price_usd,
                        "liquidity_usd": c.pair.liquidity_usd,
                        "change_1h": c.pair.change_1h,
                        "score": round(c.score, 4),
                        "components": {k: round(v, 4) for k, v in c.components.items()},
                        "safety_score": c.safety.score,
                        "safety_rejections": c.safety.rejections,
                        "entry_rejections": c.rejections,
                        "tradeable": c.tradeable,
                    }
                    for c in rows
                ],
                "disclaimer": DISCLAIMER,
            },
            indent=2,
        ))
        return 0

    print(f"\n{BOLD}Scanned {len(pairs)} pairs — {rejected} rejected by the safety gate{RESET}\n")
    header = (f"{'SCORE':>6}  {'CHAIN':<14} {'TOKEN':<12} {'LIQ':>10} {'1H':>8} "
              f"{'SAFE':>5}  WHY NOT")
    print(BOLD + header + RESET)
    print("-" * len(header))
    for c in rows[: args.limit]:
        p = c.pair
        colour = GREEN if c.tradeable else DIM
        liquidity = f"${p.liquidity_usd:,.0f}" if p.liquidity_usd else "-"
        why = "; ".join(c.safety.rejections + c.rejections)[:44] or f"{GREEN}TRADEABLE{RESET}"
        print(f"{colour}{c.score:>6.2f}{RESET}  {p.chain.label:<14} {p.base_symbol[:12]:<12} "
              f"{liquidity:>10} {_pct(p.change_1h):>8} {c.safety.score:>5}  {why}")
    print(f"\n{DIM}{DISCLAIMER}{RESET}\n")
    return 0


def cmd_run(cfg: DeskConfig, args: argparse.Namespace) -> int:
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    desk = build_desk(cfg, args)

    mode = cfg.execution.mode
    colour = RED if mode == "live" else CYAN
    print(f"\n{BOLD}Trading desk{RESET}  mode={colour}{mode}{RESET}  "
          f"chains={', '.join(c.label for c in cfg.chains)}")
    print(f"Equity {_money(desk.portfolio.equity_usd)}  "
          f"target {_money(cfg.target_usd)}  "
          f"poll every {cfg.poll_interval_seconds:.0f}s")
    if mode == "live":
        blockers = desk.executor.preflight() if isinstance(desk.executor, LiveExecutor) else []
        if blockers:
            print(f"{RED}Live mode is not armed:{RESET}")
            for blocker in blockers:
                print(f"  - {blocker}")
            print(f"{DIM}Nothing will be submitted. See trading_desk/execution/live.py.{RESET}\n")
            return 1
        signer = getattr(desk.executor, "signer", None)
        wallets = ", ".join(
            f"{chain.label}: {sub.wallet_address(chain)}"
            for chain, sub in getattr(signer, "signers", {}).items()
        )
        print(f"Wallets  {wallets or 'none'}")
        if args.arm:
            print(f"{RED}{BOLD}ARMED — real transactions will be broadcast.{RESET} "
                  f"Per-order cap ${args.max_order_usd:,.2f}.")
        else:
            print(f"{YELLOW}Not armed:{RESET} orders will be built and simulated but "
                  f"{BOLD}not broadcast{RESET}. Add --arm to trade for real.")
    for line in _risk_banner(cfg):
        print(line)
    print()

    def on_tick(result) -> None:
        stamp = f"{DIM}tick {desk.ticks}{RESET}"
        print(f"{stamp}  equity {_money(result.equity_usd)}  "
              f"cash {_money(result.cash_usd)}  "
              f"scanned {result.scanned}  "
              f"blocked {result.safety_rejected}  "
              f"open {len(desk.portfolio.open_positions)}")
        for entry in result.entries:
            print(f"  {GREEN}BUY {RESET} {entry}")
        for exit_ in result.exits:
            colour = GREEN if "+" in exit_.split()[2] else RED
            print(f"  {colour}SELL{RESET} {exit_}")
        if result.halted_reason:
            print(f"  {YELLOW}HALTED: {result.halted_reason}{RESET}")
        for error in result.errors[: args.max_errors]:
            print(f"  {DIM}! {error}{RESET}")

    desk.run(max_ticks=args.ticks, on_tick=on_tick)

    print(f"\n{BOLD}Session over{RESET}")
    _print_stats(desk.portfolio.stats(), cfg)
    if desk.journal:
        desk.journal.close()
    return 0


def cmd_serve(cfg: DeskConfig, args: argparse.Namespace) -> int:
    """Run the desk with a local dashboard in front of it."""
    from .web.runner import DeskRunner
    from .web.server import serve as serve_http

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    desk = build_desk(cfg, args)

    if cfg.execution.mode == "live":
        blockers = desk.executor.preflight() if isinstance(desk.executor, LiveExecutor) else []
        if blockers:
            print(f"{RED}Live mode is not armed:{RESET}")
            for blocker in blockers:
                print(f"  - {blocker}")
            return 1

    runner = DeskRunner(desk)
    from pathlib import Path

    httpd = serve_http(
        runner,
        host=args.host,
        port=args.port,
        config_path=Path(args.config) if args.config else None,
    )

    mode = cfg.execution.mode
    colour = RED if mode == "live" else CYAN
    print(f"\n{BOLD}Trading desk{RESET}  mode={colour}{mode}{RESET}  "
          f"chains={', '.join(c.label for c in cfg.chains)}")
    print(f"{BOLD}Dashboard{RESET}  http://{args.host}:{args.port}")
    if args.host not in ("127.0.0.1", "localhost"):
        print(f"{RED}Warning:{RESET} bound to {args.host} with no authentication — "
              f"anyone who can reach this port can flatten your book.")
    if mode == "live" and getattr(args, "arm", False):
        print(f"{RED}{BOLD}ARMED — real transactions will be broadcast.{RESET}")
    for line in _risk_banner(cfg):
        print(line)
    print(f"\n{DIM}Ctrl-C to stop. Open positions are left in place.{RESET}\n")

    try:
        while True:
            # The desk runs on its own thread; this one only waits for Ctrl-C.
            runner._stop.wait(3600)
    except KeyboardInterrupt:
        print(f"\n{DIM}Stopping...{RESET}")
    finally:
        httpd.shutdown()
        runner.stop()
        if desk.journal:
            desk.journal.close()

    _print_stats(desk.portfolio.stats(), cfg)
    return 0


def cmd_status(cfg: DeskConfig, args: argparse.Namespace) -> int:
    with Journal(cfg.journal_path) as journal:
        portfolio = journal.load_portfolio(cfg.starting_capital_usd)
        stats = portfolio.stats()
        drawdown = journal.max_drawdown_pct()

        if args.json:
            print(json.dumps({**stats, "max_drawdown_pct": drawdown}, indent=2, default=str))
            return 0

        print(f"\n{BOLD}Portfolio{RESET}")
        _print_stats(stats, cfg)
        print(f"  Max drawdown            {drawdown * 100:.1f}%")

        if portfolio.positions:
            print(f"\n{BOLD}Open positions{RESET}")
            header = f"  {'TOKEN':<12} {'CHAIN':<14} {'VALUE':>10} {'MULT':>7} {'STOP':>12}"
            print(BOLD + header + RESET)
            for position in portfolio.open_positions:
                colour = GREEN if position.multiple >= 1 else RED
                print(f"  {position.symbol[:12]:<12} {position.chain.label:<14} "
                      f"{_money(position.market_value_usd):>10} "
                      f"{colour}{position.multiple:>6.2f}x{RESET} "
                      f"${position.stop_price:>11.8g}")

        trades = journal.recent_trades(limit=args.limit)
        if trades:
            print(f"\n{BOLD}Recent trades{RESET}")
            for row in trades:
                colour = GREEN if row["pnl_usd"] > 0 else RED
                print(f"  {row['symbol'][:12]:<12} {colour}{row['pnl_usd']:>+8.2f} USD "
                      f"({row['return_pct'] * 100:>+6.1f}%){RESET}  {row['reason']}")
        print()
    return 0


def _print_stats(stats: dict, cfg: DeskConfig) -> None:
    equity = stats["equity_usd"]
    colour = GREEN if stats["total_return_pct"] >= 0 else RED
    print(f"  Equity                  {_money(equity)}  "
          f"{colour}({stats['total_return_pct'] * 100:+.1f}%){RESET}")
    print(f"  Cash                    {_money(stats['cash_usd'])}")
    print(f"  Open positions          {stats['open_positions']}")
    print(f"  Closed trades           {stats['trades']} "
          f"({stats['wins']}W / {stats['losses']}L, "
          f"{stats['win_rate'] * 100:.0f}% win rate)")
    if stats["trades"]:
        pf = stats["profit_factor"]
        print(f"  Avg win / avg loss      {_money(stats['avg_win_usd'])} / "
              f"{_money(stats['avg_loss_usd'])}")
        print(f"  Profit factor           {'inf' if pf is None else f'{pf:.2f}'}")
        print(f"  Best / worst trade      {_money(stats['best_usd'])} / "
              f"{_money(stats['worst_usd'])}")
    print(f"  Fees and gas paid       {_money(stats['fees_paid_usd'])}")
    if equity > 0:
        print(f"  Remaining to target     {cfg.target_usd / equity:,.0f}x")


def cmd_panic(cfg: DeskConfig, args: argparse.Namespace) -> int:
    desk = build_desk(cfg, args)
    if not desk.portfolio.positions:
        print("No open positions.")
        return 0
    print(f"{YELLOW}Flattening {len(desk.portfolio.positions)} positions...{RESET}")
    for line in desk.close_all():
        print(f"  {line}")
    _print_stats(desk.portfolio.stats(), cfg)
    if desk.journal:
        desk.journal.close()
    return 0


def cmd_doctor(cfg: DeskConfig, args: argparse.Namespace) -> int:
    problems = validate_config(cfg)
    print(f"\n{BOLD}Configuration{RESET}")
    if problems:
        for problem in problems:
            print(f"  {RED}x{RESET} {problem}")
    else:
        print(f"  {GREEN}✓{RESET} valid")

    print(f"\n{BOLD}Chains{RESET}")
    for chain in cfg.chains:
        if chain in (Chain.SOLANA, Chain.BNB):
            print(f"  {GREEN}✓{RESET} {chain.label}: DexScreener feed (price, depth, volume, txns)")
        else:
            feed = RobinhoodFeed(
                rpc_url=args.rpc_url,
                explorer_api=args.explorer_api,
                v3_factory=args.v3_factory,
                weth=args.weth,
                native_usd_price=args.native_usd,
            )
            if feed.priced:
                print(f"  {GREEN}✓{RESET} {chain.label}: explorer + RPC, prices available")
            else:
                print(f"  {YELLOW}!{RESET} {chain.label}: needs --v3-factory, --weth and "
                      f"--native-usd to price anything; it will be skipped")

    print(f"\n{BOLD}Execution{RESET}")
    print(f"  mode = {cfg.execution.mode}")
    if cfg.execution.mode == "paper":
        print(f"  {GREEN}✓{RESET} paper engine active — no funds at risk")
        print(f"  {DIM}Live mode additionally needs allow_live_trading and a "
              f"TransactionSigner; see execution/live.py.{RESET}")
    else:
        for blocker in LiveExecutor(cfg).preflight():
            print(f"  {RED}x{RESET} {blocker}")

    print(f"\n{BOLD}Risk{RESET}")
    banner = _risk_banner(cfg)
    if banner:
        for line in banner:
            print(f"  {line}")
    else:
        print(f"  {GREEN}✓{RESET} risk per trade is at or below the growth-optimal fraction")
    print()
    return 1 if problems else 0


# ---------------------------------------------------------------------- entry


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trading-desk",
        description=(
            "Autonomous memecoin trading desk for Solana, BNB Chain and Robinhood "
            "Chain. Paper trading by default."
        ),
    )
    parser.add_argument("-c", "--config", help="JSON config file")
    parser.add_argument("--capital", type=float, help="Override starting capital in USD")
    parser.add_argument("--target", type=float, help="Override the target in USD")
    parser.add_argument("--chains", help="Comma-separated: solana,bsc,robinhood")
    parser.add_argument("--journal", help="Path to the SQLite journal")
    parser.add_argument("--no-journal", action="store_true", help="Run without persistence")
    parser.add_argument("--rpc-url", default=DEFAULT_RPC_URL, help="Robinhood Chain JSON-RPC")
    parser.add_argument("--explorer-api", default=DEFAULT_EXPLORER_API, help="Blockscout v2 API")
    parser.add_argument(
        "--solana-rpc",
        default="https://api.mainnet-beta.solana.com",
        help="Solana JSON-RPC endpoint used for signing and simulation",
    )
    parser.add_argument(
        "--bnb-rpc",
        default="https://bsc-dataseed.binance.org",
        help="BNB Chain JSON-RPC endpoint used for signing and simulation",
    )
    parser.add_argument("--v3-factory", help="Uniswap V3 factory on Robinhood Chain")
    parser.add_argument("--weth", help="Wrapped ETH address on Robinhood Chain")
    parser.add_argument(
        "--native-usd",
        type=float,
        help="USD price of Robinhood Chain's native asset, needed to price its pools",
    )
    parser.add_argument("--json", action="store_true", help="Machine-readable output")

    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="What the target actually requires")
    plan.add_argument("--runs", type=int, default=5000)
    plan.add_argument("--trades", type=int, default=2000)
    plan.add_argument("--trades-per-day", type=float, default=6.0)
    plan.set_defaults(func=cmd_plan)

    simulate = sub.add_parser("simulate", help="Monte-Carlo the strategy forward")
    simulate.add_argument("--runs", type=int, default=5000)
    simulate.add_argument("--trades", type=int, default=2000)
    simulate.add_argument("--risk", type=float, help="Override risk per trade, e.g. 0.02")
    simulate.add_argument("--seed", type=int, default=7)
    simulate.set_defaults(func=cmd_simulate)

    scan = sub.add_parser("scan", help="One discovery + screening pass, no trading")
    scan.add_argument("--limit", type=int, default=25)
    scan.add_argument("--all", action="store_true", help="Include safety-rejected pairs")
    scan.set_defaults(func=cmd_scan)

    run = sub.add_parser("run", help="Run the autonomous loop")
    run.add_argument("--ticks", type=int, help="Stop after N ticks (default: run forever)")
    run.add_argument("--interval", type=float, help="Seconds between ticks")
    run.add_argument("--live", action="store_true", help="Attempt live mode (needs a signer)")
    run.add_argument(
        "--arm",
        action="store_true",
        help=(
            "Broadcast real transactions. Without this, live mode builds and "
            "simulates every order but sends nothing."
        ),
    )
    run.add_argument(
        "--max-order-usd",
        type=float,
        default=25.0,
        help="Hard per-order ceiling enforced by the signer itself (default: 25)",
    )
    run.add_argument(
        "--failure-rate",
        type=float,
        default=0.0,
        help="Simulate this share of failed transactions in paper mode, e.g. 0.05",
    )
    run.add_argument("--max-errors", type=int, default=3, help="Errors to print per tick")
    run.add_argument("-v", "--verbose", action="store_true")
    run.set_defaults(func=cmd_run)

    serve_cmd = sub.add_parser("serve", help="Run the desk with a local web dashboard")
    serve_cmd.add_argument("--host", default="127.0.0.1", help="Bind address (default: localhost)")
    serve_cmd.add_argument("--port", type=int, default=8787, help="Dashboard port")
    serve_cmd.add_argument("--interval", type=float, help="Seconds between ticks")
    serve_cmd.add_argument("--live", action="store_true", help="Attempt live mode")
    serve_cmd.add_argument(
        "--arm",
        action="store_true",
        help="Broadcast real transactions (live mode only)",
    )
    serve_cmd.add_argument("--max-order-usd", type=float, default=25.0,
                           help="Hard per-order ceiling enforced by the signer")
    serve_cmd.add_argument("--failure-rate", type=float, default=0.0,
                           help="Simulate this share of failed transactions in paper mode")
    serve_cmd.add_argument("-v", "--verbose", action="store_true")
    serve_cmd.set_defaults(func=cmd_serve)

    status = sub.add_parser("status", help="Portfolio and performance")
    status.add_argument("--limit", type=int, default=10)
    status.set_defaults(func=cmd_status)

    panic = sub.add_parser("panic", help="Flatten every open position now")
    panic.set_defaults(func=cmd_panic)

    doctor = sub.add_parser("doctor", help="Validate config and report live-trading blockers")
    doctor.set_defaults(func=cmd_doctor)
    return parser


def apply_overrides(cfg: DeskConfig, args: argparse.Namespace) -> None:
    if args.capital is not None:
        cfg.starting_capital_usd = args.capital
    if args.target is not None:
        cfg.target_usd = args.target
    if args.journal:
        cfg.journal_path = args.journal
    if args.chains:
        cfg.chains = tuple(Chain(c.strip()) for c in args.chains.split(",") if c.strip())
    # `is not None`, not truthiness: --interval 0 is a legitimate request for
    # back-to-back ticks (and is what the tests run at).
    if getattr(args, "interval", None) is not None:
        cfg.poll_interval_seconds = args.interval
    if getattr(args, "live", False):
        cfg.execution.mode = "live"


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Subcommands that don't wire a desk still read these attributes.
    for attr, default in (("no_journal", False), ("failure_rate", 0.0)):
        if not hasattr(args, attr):
            setattr(args, attr, default)

    try:
        cfg, warnings = load_config(args.config)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"{RED}Could not read config: {exc}{RESET}", file=sys.stderr)
        return 1
    for warning in warnings:
        print(f"{YELLOW}Config: {warning}{RESET}", file=sys.stderr)

    try:
        apply_overrides(cfg, args)
    except ValueError as exc:
        print(f"{RED}{exc}{RESET}", file=sys.stderr)
        return 1

    problems = validate_config(cfg)
    if problems and args.command != "doctor":
        for problem in problems:
            print(f"{RED}Config error: {problem}{RESET}", file=sys.stderr)
        return 1

    return args.func(cfg, args)


if __name__ == "__main__":
    raise SystemExit(main())
