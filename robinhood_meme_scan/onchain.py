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


_V3_POOL_ABI = [
    {
        "inputs": [],
        "name": "slot0",
        "outputs": [
            {"internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"},
            {"internalType": "int24", "name": "tick", "type": "int24"},
            {"internalType": "uint16", "name": "observationIndex", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinality", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinalityNext", "type": "uint16"},
            {"internalType": "uint8", "name": "feeProtocol", "type": "uint8"},
            {"internalType": "bool", "name": "unlocked", "type": "bool"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "token0",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
]

_Q96 = 2**96


@dataclass
class PoolState:
    """Spot price and both sides of a V3 pool's balance.

    ``price_in_quote`` is one whole token priced in whole quote units (e.g.
    TOKEN/WETH), decimals already applied. It is a spot read of slot0, so it
    is the marginal price, not the price a real order would average.
    """

    pool_address: str
    fee_tier: int
    price_in_quote: Optional[float]
    token_balance: int
    quote_balance: int


def read_pool_state(
    w3: Web3,
    pool_address: str,
    token_address: str,
    quote_address: str,
    token_decimals: int = 18,
    quote_decimals: int = 18,
    fee_tier: int = 0,
) -> PoolState:
    """Read spot price and reserves from a Uniswap V3 pool.

    Price comes from slot0's sqrtPriceX96, which is token1-per-token0 scaled by
    2**96; which of the two the memecoin is depends on address ordering, so
    token0() decides whether to invert. A pool that can't be read returns a
    None price rather than a guessed one — callers treat that as "unknown".
    """
    pool = Web3.to_checksum_address(pool_address)
    token = Web3.to_checksum_address(token_address)
    quote = Web3.to_checksum_address(quote_address)

    price: Optional[float] = None
    try:
        contract = w3.eth.contract(address=pool, abi=_V3_POOL_ABI)
        sqrt_price_x96 = contract.functions.slot0().call()[0]
        token0 = contract.functions.token0().call()
        if sqrt_price_x96:
            # (sqrtP / 2**96)**2 is token1 per token0 in raw units.
            ratio = (sqrt_price_x96 / _Q96) ** 2
            if Web3.to_checksum_address(token0) == token:
                price = ratio * (10 ** (token_decimals - quote_decimals))
            elif ratio > 0:
                price = (1 / ratio) * (10 ** (token_decimals - quote_decimals))
    except Exception:
        price = None

    balances = []
    for asset in (token, quote):
        try:
            erc20 = w3.eth.contract(address=asset, abi=_ERC20_BALANCE_ABI)
            balances.append(int(erc20.functions.balanceOf(pool).call()))
        except Exception:
            balances.append(0)

    return PoolState(
        pool_address=pool_address,
        fee_tier=fee_tier,
        price_in_quote=price,
        token_balance=balances[0],
        quote_balance=balances[1],
    )
