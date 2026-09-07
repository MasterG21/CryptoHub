"""Order execution. Paper is wired end to end; live needs a signer you supply."""

from .base import (
    ExecutionError,
    Executor,
    SlippageExceeded,
    buy_impact_pct,
    round_trip_cost_pct,
    sell_impact_pct,
)
from .live import LiveExecutor, LiveTradingUnavailable, TransactionSigner
from .paper import PaperExecutor

__all__ = [
    "ExecutionError",
    "Executor",
    "SlippageExceeded",
    "PaperExecutor",
    "LiveExecutor",
    "LiveTradingUnavailable",
    "TransactionSigner",
    "buy_impact_pct",
    "sell_impact_pct",
    "round_trip_cost_pct",
]
