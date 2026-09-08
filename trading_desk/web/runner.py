"""Runs the desk on a background thread and exposes a snapshot for the UI.

The dashboard must never be able to affect trading. It reads a snapshot taken
under a lock and issues control requests that the trading thread picks up at
the start of its next tick — a browser tab refreshing every two seconds does
not get to interleave with position management.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any, Optional

from ..desk import TickResult, TradingDesk
from ..execution.live import LiveExecutor
from ..growth import stall_equity
from ..models import ExitReason


class DeskRunner:
    """Owns the desk, its thread, and the state the web layer reads."""

    def __init__(self, desk: TradingDesk, activity_limit: int = 200):
        self.desk = desk
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._activity: deque[dict] = deque(maxlen=activity_limit)
        self._last_tick: Optional[TickResult] = None
        self._started_at = time.time()
        self._tick_count = 0
        self._panic_requested = False
        self._last_error: Optional[str] = None
        # Last decision logged per token, so a candidate rejected for the same
        # reason on fifty consecutive ticks produces one line, not fifty. The
        # log is for changes; the reviews panel shows current state.
        self._last_decision: dict[str, str] = {}

    # ------------------------------------------------------------- lifecycle

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="desk", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                if self._panic_requested:
                    self._run_panic()
                result = self.desk.tick()
                with self._lock:
                    self._tick_count += 1
                    self._last_tick = result
                    self._last_error = None
                    self._record(result)
            except Exception as exc:  # noqa: BLE001 - a bad tick must not kill the thread
                with self._lock:
                    self._last_error = str(exc)
                    self._log("error", f"tick failed: {exc}")
            self._stop.wait(max(1.0, self.desk.config.poll_interval_seconds))

    def _run_panic(self) -> None:
        closed = self.desk.close_all(ExitReason.MANUAL)
        with self._lock:
            self._panic_requested = False
            self.desk.paused = True
            for line in closed:
                self._log("exit", f"PANIC {line}")
            if not closed:
                self._log("note", "panic: nothing open to close")

    # --------------------------------------------------------------- control

    def pause(self) -> str:
        self.desk.paused = True
        with self._lock:
            self._log("note", "paused by operator — exits still run")
        return "paused"

    def resume(self) -> str:
        self.desk.paused = False
        self.desk.risk.clear_halt()
        with self._lock:
            self._log("note", "resumed by operator")
        return "running"

    def panic(self) -> str:
        """Queue a flatten. Executed by the trading thread, never by the web one."""
        with self._lock:
            self._panic_requested = True
            self._log("note", "panic requested — flattening on next tick")
        return "flattening"

    # ------------------------------------------------------------- recording

    def _log(self, kind: str, message: str, agent: Optional[str] = None) -> None:
        self._activity.appendleft(
            {"at": time.time(), "kind": kind, "agent": agent, "message": message}
        )

    def _record(self, result: TickResult) -> None:
        for entry in result.entries:
            self._log("entry", entry)
        for exit_ in result.exits:
            self._log("exit", exit_)
        for error in result.errors[:3]:
            self._log("error", error)
        # One line per blocked candidate, attributed to the agent that blocked
        # it — this is the log that makes the committee worth having. Only
        # changes are logged: the same token refused for the same reason every
        # tick would otherwise bury everything else.
        seen: set[str] = set()
        for review in result.reviews[:12]:
            key = review.pair.key
            seen.add(key)
            blocker = review.blocked_by
            if blocker:
                kind, agent = "veto", blocker.agent
                message = f"{review.pair.base_symbol}: {blocker.reason}"
            elif review.approved:
                kind, agent = "approved", "PALERMO"
                message = (
                    f"{review.pair.base_symbol}: cleared all ten, "
                    f"${review.approved_usd or 0:.2f}"
                )
            else:
                continue
            if self._last_decision.get(key) == message:
                continue
            self._last_decision[key] = message
            self._log(kind, message, agent=agent)

        # Forget tokens that dropped out of the scan, so if one comes back its
        # verdict is reported again rather than suppressed as a duplicate.
        for key in [k for k in self._last_decision if k not in seen]:
            del self._last_decision[key]

    # -------------------------------------------------------------- snapshot

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            desk, portfolio, cfg = self.desk, self.desk.portfolio, self.desk.config
            stats = portfolio.stats()
            last = self._last_tick

            executor = desk.executor
            live = isinstance(executor, LiveExecutor)
            signer = getattr(executor, "signer", None)
            armed = bool(
                live and signer and not getattr(getattr(signer, "limits", None), "dry_run", True)
            )
            wallets = {}
            for chain, sub in getattr(signer, "signers", {}).items():
                try:
                    wallets[chain.label] = sub.wallet_address(chain)
                except Exception as exc:  # noqa: BLE001 - a missing key is not fatal here
                    wallets[chain.label] = f"unavailable ({type(exc).__name__})"

            # What still stands between this config and a real order. Surfaced so
            # the dashboard can offer the way out instead of the operator being
            # stuck with a desk that will not trade and will not say why.
            blockers = executor.preflight() if live else []

            floor = stall_equity(
                cfg.risk.risk_per_trade_pct,
                cfg.risk.min_position_usd,
                cfg.strategy.stop_loss_pct,
            )
            equity = stats["equity_usd"]

            return {
                "mode": {
                    "execution": cfg.execution.mode,
                    "armed": armed,
                    "paused": desk.paused,
                    "wallets": wallets,
                    "chains": [c.label for c in cfg.chains],
                    "blockers": blockers,
                    "can_trade": not blockers,
                },
                "equity": {
                    "usd": equity,
                    "cash_usd": stats["cash_usd"],
                    "start_usd": portfolio.starting_cash_usd,
                    "return_pct": stats["total_return_pct"],
                    "realized_usd": portfolio.realized_pnl_usd,
                    "unrealized_usd": portfolio.unrealized_pnl_usd,
                    "fees_usd": stats["fees_paid_usd"],
                    "target_usd": cfg.target_usd,
                    "pct_of_target": equity / cfg.target_usd if cfg.target_usd else 0,
                    "untradeable_below_usd": floor,
                    "room_to_floor_pct": max(0.0, 1 - floor / equity) if equity > 0 else 0.0,
                },
                "performance": {
                    "trades": stats["trades"],
                    "wins": stats["wins"],
                    "losses": stats["losses"],
                    "win_rate": stats["win_rate"],
                    "profit_factor": stats["profit_factor"],
                    "best_usd": stats["best_usd"],
                    "worst_usd": stats["worst_usd"],
                },
                "gas": {
                    "balances": dict(getattr(desk, "native_balances", {})),
                    "floors": {
                        c.value: cfg.native_reserve_for(c) for c in cfg.chains
                    },
                    "symbols": {c.value: c.native_symbol for c in cfg.chains},
                    "warnings": last.gas_warnings if last else [],
                },
                "risk": {
                    "halted_reason": last.halted_reason if last else None,
                    "consecutive_losses": desk.risk.state.consecutive_losses,
                    "max_consecutive_losses": cfg.risk.max_consecutive_losses,
                    "day_start_equity": desk.risk.state.day_start_equity,
                    "daily_loss_limit_pct": cfg.risk.daily_loss_limit_pct,
                    "slots_used": len(portfolio.open_positions),
                    "slots_total": cfg.risk.max_concurrent_positions,
                },
                "tick": {
                    "count": self._tick_count,
                    "uptime_seconds": time.time() - self._started_at,
                    "interval_seconds": cfg.poll_interval_seconds,
                    "scanned": last.scanned if last else 0,
                    "blocked": last.safety_rejected if last else 0,
                    "scored": last.scored if last else 0,
                    "last_error": self._last_error,
                },
                "positions": [
                    {
                        "symbol": p.symbol,
                        "chain": p.chain.label,
                        "address": p.token_address,
                        "quantity": p.quantity,
                        "entry": p.avg_entry_price,
                        "last": p.last_price,
                        "stop": p.stop_price,
                        "multiple": p.multiple,
                        "value_usd": p.market_value_usd,
                        "unrealized_usd": p.unrealized_usd,
                        "age_minutes": p.age_minutes,
                        "trailing_armed": p.trailing_armed,
                        "scale_outs": p.scale_outs_done,
                    }
                    for p in portfolio.open_positions
                ],
                "agents": self._agent_state(),
                "reviews": [r.to_dict() for r in (last.reviews[:10] if last else [])],
                "activity": list(self._activity)[:60],
                "trades": [
                    {
                        "symbol": t.symbol,
                        "chain": t.chain.label,
                        "pnl_usd": t.pnl_usd,
                        "return_pct": t.return_pct,
                        "reason": t.reason,
                        "minutes": t.holding_minutes,
                        "closed_at": t.closed_at,
                    }
                    for t in reversed(portfolio.closed_trades[-15:])
                ],
                "equity_curve": self._equity_curve(),
            }

    def _agent_state(self) -> list[dict]:
        """Per-agent tallies from the most recent tick, for the roster strip."""
        roster = self.desk.committee.roster
        last = self._last_tick
        counts: dict[str, dict] = {
            a["name"]: {**a, "passed": 0, "vetoed": 0, "skipped": 0, "last": ""}
            for a in roster
        }
        for review in (last.reviews if last else []):
            for verdict in review.verdicts:
                bucket = counts.get(verdict.agent)
                if bucket is None:
                    continue
                if verdict.stance.value == "veto":
                    bucket["vetoed"] += 1
                    bucket["last"] = verdict.reason
                elif verdict.stance.value == "skipped":
                    bucket["skipped"] += 1
                else:
                    bucket["passed"] += 1
                    if not bucket["last"]:
                        bucket["last"] = verdict.reason
        return list(counts.values())

    def _equity_curve(self) -> list[list[float]]:
        journal = self.desk.journal
        if journal is None:
            return []
        try:
            return [[ts, value] for ts, value in journal.equity_curve(limit=240)]
        except Exception:  # noqa: BLE001 - the chart is not worth an outage
            return []
