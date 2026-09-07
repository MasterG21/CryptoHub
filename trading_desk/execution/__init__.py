"""Order execution. Paper is wired end to end; live needs a signer you supply."""

from .base import (
    ExecutionError,
    Executor,
    SlippageExceeded,
    buy_impact_pct,
    round_trip_cost_pct,
    sell_impact_pct,
)
from .live import (
    DecimalsResolver,
    LiveExecutor,
    LiveTradingUnavailable,
    TransactionSigner,
)
from .paper import PaperExecutor
from .signers import (
    EvmSigner,
    KeyLoadError,
    MultiChainSigner,
    SignerError,
    SignerLimits,
    SolanaSigner,
)

__all__ = [
    "ExecutionError",
    "Executor",
    "SlippageExceeded",
    "PaperExecutor",
    "LiveExecutor",
    "LiveTradingUnavailable",
    "TransactionSigner",
    "DecimalsResolver",
    "SolanaSigner",
    "EvmSigner",
    "MultiChainSigner",
    "SignerLimits",
    "SignerError",
    "KeyLoadError",
    "buy_impact_pct",
    "sell_impact_pct",
    "round_trip_cost_pct",
]
