"""Durable record of everything the desk did, in SQLite.

Two jobs. The first is the audit trail: every fill, every closed trade, an
equity point per tick. The second is restart safety — the desk must be able to
die mid-session and come back holding the same positions, the same cash and the
same risk counters. A bot that forgets it is down 20% today because it was
restarted has no daily loss limit at all.

Open positions are stored as a full replacement snapshot each save rather than
incrementally, so the database can never drift from the portfolio in memory.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any, Optional

from .models import Chain, Fill, Position
from .portfolio import ClosedTrade, Portfolio
from .risk import RiskState

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    chain TEXT NOT NULL,
    token_address TEXT NOT NULL,
    symbol TEXT,
    side TEXT NOT NULL,
    quantity REAL NOT NULL,
    price REAL NOT NULL,
    fee_usd REAL NOT NULL,
    gas_usd REAL NOT NULL,
    slippage_pct REAL NOT NULL,
    net_usd REAL NOT NULL,
    reason TEXT,
    tx_ref TEXT
);
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chain TEXT NOT NULL,
    token_address TEXT NOT NULL,
    symbol TEXT,
    quantity REAL NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL NOT NULL,
    cost_usd REAL NOT NULL,
    proceeds_usd REAL NOT NULL,
    pnl_usd REAL NOT NULL,
    return_pct REAL NOT NULL,
    reason TEXT,
    opened_at REAL NOT NULL,
    closed_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS equity (
    ts REAL PRIMARY KEY,
    equity_usd REAL NOT NULL,
    cash_usd REAL NOT NULL,
    positions_value_usd REAL NOT NULL,
    open_positions INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS open_positions (
    key TEXT PRIMARY KEY,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trades_closed_at ON trades (closed_at);
CREATE INDEX IF NOT EXISTS idx_fills_ts ON fills (ts);
"""

_POSITION_FIELDS = (
    "chain",
    "token_address",
    "symbol",
    "quantity",
    "avg_entry_price",
    "cost_basis_usd",
    "stop_price",
    "opened_at",
    "high_water_price",
    "entry_liquidity_usd",
    "last_price",
    "last_liquidity_usd",
    "realized_usd",
    "scale_outs_done",
    "trailing_armed",
    "pair_address",
    "initial_quantity",
)


class Journal:
    """SQLite-backed journal, safe to share between the desk and web threads.

    ``check_same_thread=False`` plus one lock, because the dashboard serves
    reads on HTTP handler threads while the desk writes on its own. Without
    this SQLite refuses every cross-thread call and the desk silently stops
    persisting — no equity curve, and no restart safety, which is the thing
    the journal exists for.
    """

    def __init__(self, path: str = "desk_journal.sqlite3"):
        self.path = path
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with self._lock:
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    def close(self) -> None:
        with self._lock:
            self.conn.close()

    def reset(self) -> None:
        """Wipe every record and start the account over.

        Used when the operator changes the practice budget: keeping the old
        equity curve and win rate against a different starting balance would
        make every reported percentage meaningless.
        """
        with self._lock:
            for table in ("fills", "trades", "equity", "open_positions", "meta"):
                self.conn.execute(f"DELETE FROM {table}")
            self.conn.commit()

    def __enter__(self) -> "Journal":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ----------------------------------------------------------------- writes

    def record_fill(self, fill: Fill) -> None:
        with self._lock:
            self.conn.execute(
                """INSERT INTO fills (ts, chain, token_address, symbol, side, quantity,
                                      price, fee_usd, gas_usd, slippage_pct, net_usd, reason, tx_ref)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    fill.timestamp,
                    fill.order.chain.value,
                    fill.order.token_address,
                    fill.order.symbol,
                    fill.order.side.value,
                    fill.quantity,
                    fill.price,
                    fill.fee_usd,
                    fill.gas_usd,
                    fill.slippage_pct,
                    fill.net_usd,
                    fill.order.reason,
                    fill.tx_ref,
                ),
            )
            self.conn.commit()

    def record_trade(self, trade: ClosedTrade) -> None:
        with self._lock:
            self.conn.execute(
                """INSERT INTO trades (chain, token_address, symbol, quantity, entry_price,
                                       exit_price, cost_usd, proceeds_usd, pnl_usd, return_pct,
                                       reason, opened_at, closed_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    trade.chain.value,
                    trade.token_address,
                    trade.symbol,
                    trade.quantity,
                    trade.entry_price,
                    trade.exit_price,
                    trade.cost_usd,
                    trade.proceeds_usd,
                    trade.pnl_usd,
                    trade.return_pct,
                    trade.reason,
                    trade.opened_at,
                    trade.closed_at,
                ),
            )
            self.conn.commit()

    def snapshot_equity(self, portfolio: Portfolio, ts: Optional[float] = None) -> None:
        with self._lock:
            self.conn.execute(
                """INSERT OR REPLACE INTO equity
                   (ts, equity_usd, cash_usd, positions_value_usd, open_positions)
                   VALUES (?,?,?,?,?)""",
                (
                    ts if ts is not None else time.time(),
                    portfolio.equity_usd,
                    portfolio.cash_usd,
                    portfolio.positions_value_usd,
                    len(portfolio.positions),
                ),
            )
            self.conn.commit()

    def save_state(
        self,
        portfolio: Portfolio,
        risk_state: RiskState,
        recent_exits: Optional[dict[str, float]] = None,
    ) -> None:
        with self._lock:
            """Replace the stored open book and risk counters with what is live now."""
            self.conn.execute("DELETE FROM open_positions")
            self.conn.executemany(
                "INSERT INTO open_positions (key, data) VALUES (?,?)",
                [
                    (
                        key,
                        json.dumps(
                            {
                                f: (
                                    position.chain.value
                                    if f == "chain"
                                    else getattr(position, f)
                                )
                                for f in _POSITION_FIELDS
                            }
                        ),
                    )
                    for key, position in portfolio.positions.items()
                ],
            )
            self._set_meta("cash_usd", portfolio.cash_usd)
            self._set_meta("starting_cash_usd", portfolio.starting_cash_usd)
            self._set_meta("fees_paid_usd", portfolio.fees_paid_usd)
            self._set_meta("risk_state", risk_state.__dict__)
            # Persisted so a crash-loop cannot churn back into a token the desk
            # just exited: an in-memory cooldown resets on every restart.
            self._set_meta("recent_exits", recent_exits or {})
            self.conn.commit()

    def _set_meta(self, key: str, value: Any) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?,?)",
            (key, json.dumps(value)),
        )

    # ------------------------------------------------------------------ reads

    def get_meta(self, key: str, default: Any = None) -> Any:
        with self._lock:
            row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
            if row is None:
                return default
            try:
                return json.loads(row["value"])
            except json.JSONDecodeError:
                return default

    def load_portfolio(self, starting_cash_usd: float) -> Portfolio:
        with self._lock:
            """Rebuild the portfolio from disk, or start fresh if nothing is stored.

            Closed trades are reloaded too, so win rate and profit factor survive a
            restart instead of resetting to a flattering empty slate.
            """
            stored_start = self.get_meta("starting_cash_usd")
            portfolio = Portfolio(
                starting_cash_usd=stored_start if stored_start is not None else starting_cash_usd
            )
            cash = self.get_meta("cash_usd")
            if cash is None:
                return portfolio
            portfolio.cash_usd = float(cash)
            portfolio.fees_paid_usd = float(self.get_meta("fees_paid_usd", 0.0) or 0.0)

            for row in self.conn.execute("SELECT key, data FROM open_positions"):
                raw = json.loads(row["data"])
                raw["chain"] = Chain(raw["chain"])
                portfolio.positions[row["key"]] = Position(**raw)

            for row in self.conn.execute("SELECT * FROM trades ORDER BY closed_at"):
                portfolio.closed_trades.append(
                    ClosedTrade(
                        chain=Chain(row["chain"]),
                        token_address=row["token_address"],
                        symbol=row["symbol"],
                        quantity=row["quantity"],
                        entry_price=row["entry_price"],
                        exit_price=row["exit_price"],
                        proceeds_usd=row["proceeds_usd"],
                        cost_usd=row["cost_usd"],
                        reason=row["reason"] or "",
                        opened_at=row["opened_at"],
                        closed_at=row["closed_at"],
                    )
                )
            return portfolio

    def load_risk_state(self) -> RiskState:
        with self._lock:
            raw = self.get_meta("risk_state")
            if not isinstance(raw, dict):
                return RiskState()
            known = {k: v for k, v in raw.items() if k in RiskState.__dataclass_fields__}
            return RiskState(**known)

    def load_recent_exits(self) -> dict[str, float]:
        with self._lock:
            raw = self.get_meta("recent_exits")
            if not isinstance(raw, dict):
                return {}
            return {k: float(v) for k, v in raw.items() if isinstance(v, (int, float))}

    def equity_curve(self, limit: int = 500) -> list[tuple[float, float]]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT ts, equity_usd FROM equity ORDER BY ts DESC LIMIT ?", (limit,)
            ).fetchall()
            return [(r["ts"], r["equity_usd"]) for r in reversed(rows)]

    def recent_trades(self, limit: int = 20) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(
                "SELECT * FROM trades ORDER BY closed_at DESC LIMIT ?", (limit,)
            ).fetchall()

    def max_drawdown_pct(self) -> float:
        """Worst peak-to-trough fall in the recorded equity curve."""
        peak = 0.0
        worst = 0.0
        for _, equity in self.equity_curve(limit=100_000):
            peak = max(peak, equity)
            if peak > 0:
                worst = max(worst, 1 - equity / peak)
        return worst
