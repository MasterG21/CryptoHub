"""Direct RPC checks that the explorer API doesn't cover.

Liquidity-pool lookups need a V3 factory address and a quote-token
(WETH/WBNB) address for the chain. A wrong address here is worse than no
check at all: every token would come back "no liquidity pool" on a tool
people use to judge rug risk. So before probing, `find_liquidity_pool`
confirms there is contract code at both addresses and raises
`FactoryUnavailable` if there isn't — callers report that as "couldn't
check" rather than as an absent pool. Chain presets live in chains.py;
override them with --v3-factory / --quote-token.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from web3 import Web3

from .chains import ROBINHOOD, UNISWAP_V3_FEE_TIERS

DEFAULT_RPC_URL = ROBINHOOD.rpc_url

_OWNER_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "owner",
        "outputs": [{"name": "", "type": "address"}],
        "type": "function",
    }
]

_V3_FACTORY_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "tokenA", "type": "address"},
            {"internalType": "address", "name": "tokenB", "type": "address"},
            {"internalType": "uint24", "name": "fee", "type": "uint24"},
        ],
        "name": "getPool",
        "outputs": [{"internalType": "address", "name": "pool", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    }
]

_ERC20_BALANCE_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
    }
]

# Fee tiers vary by DEX (Uniswap V3 uses 0.3%, PancakeSwap V3 uses 0.25%),
# so callers pass the right set for their chain; this is only the fallback.
_V3_FEE_TIERS = UNISWAP_V3_FEE_TIERS

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


class FactoryUnavailable(RuntimeError):
    """The configured factory or quote token isn't a contract on this chain.

    Raised instead of returning "no pool", so a misconfigured address is
    reported as an unknown rather than as evidence against the token.
    """


@dataclass
class OwnershipStatus:
    supported: bool  # False if the contract has no owner() function
    owner: Optional[str] = None

    @property
    def renounced(self) -> bool:
        return self.supported and self.owner == ZERO_ADDRESS


@dataclass
class LiquidityPool:
    fee_tier: int
    pool_address: str
    token_balance: int


def get_web3(rpc_url: str = DEFAULT_RPC_URL) -> Web3:
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    return w3


def check_ownership(w3: Web3, token_address: str) -> OwnershipStatus:
    contract = w3.eth.contract(address=Web3.to_checksum_address(token_address), abi=_OWNER_ABI)
    try:
        owner = contract.functions.owner().call()
        return OwnershipStatus(supported=True, owner=owner)
    except Exception:
        # Not Ownable, or owner() reverts/doesn't exist — not necessarily a red flag.
        return OwnershipStatus(supported=False)


def _assert_is_contract(w3: Web3, address: str, label: str) -> None:
    try:
        code = w3.eth.get_code(Web3.to_checksum_address(address))
    except Exception as exc:  # bad checksum, RPC refusal, etc.
        raise FactoryUnavailable(f"could not read code at {label} {address}: {exc}") from exc
    if not code or code in (b"", b"0x", "0x"):
        raise FactoryUnavailable(
            f"no contract code at {label} {address} on this chain — "
            "check the address is right for this network"
        )


def find_liquidity_pool(
    w3: Web3,
    token_address: str,
    v3_factory: str,
    quote_token: str,
    fee_tiers: Sequence[int] = _V3_FEE_TIERS,
) -> Optional[LiquidityPool]:
    """Find a V3 pool pairing the token with the chain's quote token.

    Returns None only when the factory genuinely reports no pool at any
    fee tier. If the factory or quote token isn't a contract on this
    chain, raises FactoryUnavailable rather than implying no liquidity.
    """
    _assert_is_contract(w3, v3_factory, "V3 factory")
    _assert_is_contract(w3, quote_token, "quote token")

    factory = w3.eth.contract(address=Web3.to_checksum_address(v3_factory), abi=_V3_FACTORY_ABI)
    token = Web3.to_checksum_address(token_address)
    quote = Web3.to_checksum_address(quote_token)

    probe_failures = 0
    for fee in fee_tiers:
        try:
            pool_address = factory.functions.getPool(token, quote, fee).call()
        except Exception:
            probe_failures += 1
            continue
        if pool_address and pool_address != ZERO_ADDRESS:
            balance_contract = w3.eth.contract(address=token, abi=_ERC20_BALANCE_ABI)
            try:
                token_balance = balance_contract.functions.balanceOf(pool_address).call()
            except Exception:
                token_balance = 0
            return LiquidityPool(
                fee_tier=fee, pool_address=pool_address, token_balance=token_balance
            )

    if probe_failures == len(tuple(fee_tiers)):
        # Every call reverted — that's a broken factory ABI or endpoint,
        # not a token without a pool.
        raise FactoryUnavailable(
            f"every getPool call against {v3_factory} failed; "
            "the factory address or RPC endpoint looks wrong"
        )
    return None
