"""Per-chain configuration presets.

Everything chain-specific the screen needs — explorer API, RPC, and the
DEX factory / quote token used for the liquidity check — lives here, so
supporting a new chain is a preset rather than a code change.

A note on the DEX addresses below. This module's rule is that guessing a
contract address wrong is worse than not checking, because a bad factory
address makes every token look like it has no liquidity pool. That rule
still holds; what changed is the failure mode. `find_liquidity_pool` now
verifies there is actually contract code at the factory and quote-token
addresses before probing, and reports "couldn't check" rather than "no
pool" when there isn't. So a preset that is wrong or stale degrades to
unknown instead of silently libelling a token, which is what makes it
safe to ship known addresses rather than leaving every chain unconfigured.

The BSC addresses here are the widely published PancakeSwap V3 and WBNB
deployments, but they could not be confirmed against the live chain from
the development environment (its network policy blocks BSC RPC and
explorer endpoints). Confirm them on a block explorer before treating a
liquidity result as authoritative.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Uniswap V3's canonical fee tiers, in basis-point-hundredths.
UNISWAP_V3_FEE_TIERS = (100, 500, 3000, 10000)
# PancakeSwap V3 differs: its third tier is 0.25%, not Uniswap's 0.3%.
# Probing Uniswap's tiers on BSC would miss most real Pancake pools.
PANCAKESWAP_V3_FEE_TIERS = (100, 500, 2500, 10000)


@dataclass(frozen=True)
class Chain:
    """Everything the screen needs to know about one chain."""

    key: str
    name: str
    explorer_api: str
    explorer_url: str
    rpc_url: str
    dex_name: str
    quote_symbol: str
    v3_factory: Optional[str] = None
    quote_token: Optional[str] = None
    v3_fee_tiers: tuple[int, ...] = UNISWAP_V3_FEE_TIERS

    @property
    def liquidity_configured(self) -> bool:
        return bool(self.v3_factory and self.quote_token)


ROBINHOOD = Chain(
    key="robinhood",
    name="Robinhood Chain",
    explorer_api="https://robinhoodchain.blockscout.com/api/v2",
    explorer_url="https://robinhoodchain.blockscout.com",
    rpc_url="https://rpc.mainnet.chain.robinhood.com",
    dex_name="Uniswap V3",
    quote_symbol="WETH",
    # Left unset deliberately: the Uniswap V3 factory and WETH addresses on
    # this L2 have not been confirmed, so the liquidity check stays off
    # until someone passes them with --v3-factory / --quote-token.
    v3_factory=None,
    quote_token=None,
    v3_fee_tiers=UNISWAP_V3_FEE_TIERS,
)

BSC = Chain(
    key="bsc",
    name="BNB Smart Chain",
    explorer_api="https://bnb.blockscout.com/api/v2",
    explorer_url="https://bscscan.com",
    rpc_url="https://bsc-dataseed.bnbchain.org",
    dex_name="PancakeSwap V3",
    quote_symbol="WBNB",
    v3_factory="0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865",
    quote_token="0xbb4CdB9CbD36B01bD1cBaEBF2De08d9173bc095c",
    v3_fee_tiers=PANCAKESWAP_V3_FEE_TIERS,
)

CHAINS: dict[str, Chain] = {c.key: c for c in (ROBINHOOD, BSC)}
DEFAULT_CHAIN = ROBINHOOD.key

# Accepted spellings for --chain, so "bnb" and "binance" don't fail.
_ALIASES = {
    "bnb": "bsc",
    "binance": "bsc",
    "bnbchain": "bsc",
    "bsc": "bsc",
    "rhc": "robinhood",
    "robinhood": "robinhood",
}


def get_chain(key: str) -> Chain:
    """Look up a chain preset by key or alias."""
    normalized = _ALIASES.get(key.strip().lower())
    if normalized is None:
        known = ", ".join(sorted(CHAINS))
        raise KeyError(f"Unknown chain {key!r}. Known chains: {known}")
    return CHAINS[normalized]


def chain_choices() -> list[str]:
    return sorted(_ALIASES)
