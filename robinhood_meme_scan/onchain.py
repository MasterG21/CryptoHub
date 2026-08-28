"""Direct RPC checks that the explorer API doesn't cover.

Liquidity-pool lookups need a Uniswap V3 factory address and a WETH
address for the chain. Neither is hardcoded here: guessing a contract
address wrong would silently produce a false "no liquidity" result on a
tool people use to judge rug risk, which is worse than just skipping the
check. Pass them explicitly (--v3-factory / --weth) once you've confirmed
them on Blockscout; otherwise the liquidity check is skipped with a note.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from web3 import Web3

DEFAULT_RPC_URL = "https://rpc.mainnet.chain.robinhood.com"

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

# Standard Uniswap V3 fee tiers, checked in order when probing for a pool.
_V3_FEE_TIERS = (100, 500, 3000, 10000)

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


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


def find_liquidity_pool(
    w3: Web3, token_address: str, v3_factory: str, weth_address: str
) -> Optional[LiquidityPool]:
    factory = w3.eth.contract(address=Web3.to_checksum_address(v3_factory), abi=_V3_FACTORY_ABI)
    token = Web3.to_checksum_address(token_address)
    weth = Web3.to_checksum_address(weth_address)

    for fee in _V3_FEE_TIERS:
        try:
            pool_address = factory.functions.getPool(token, weth, fee).call()
        except Exception:
            continue
        if pool_address and pool_address != ZERO_ADDRESS:
            balance_contract = w3.eth.contract(
                address=token, abi=_ERC20_BALANCE_ABI
            )
            try:
                token_balance = balance_contract.functions.balanceOf(pool_address).call()
            except Exception:
                token_balance = 0
            return LiquidityPool(
                fee_tier=fee, pool_address=pool_address, token_balance=token_balance
            )
    return None
