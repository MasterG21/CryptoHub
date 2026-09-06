"""Liquidity probing: a misconfigured factory must read as 'unknown'.

The whole point of the guard is that a wrong factory address makes every
token look like it has no liquidity pool, which on a rug-risk tool is a
false accusation. These tests pin the distinction between "the factory
said there is no pool" and "we could not ask the factory".
"""
from unittest.mock import MagicMock

import pytest

from robinhood_meme_scan.onchain import (
    ZERO_ADDRESS,
    FactoryUnavailable,
    find_liquidity_pool,
)

FACTORY = "0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865"
QUOTE = "0xbb4CdB9CbD36B01bD1cBaEBF2De08d9173bc095c"
TOKEN = "0x1111111111111111111111111111111111111111"
POOL = "0x2222222222222222222222222222222222222222"


def make_w3(code=b"\x60\x80", get_pool=None, balance=1_000):
    """A Web3 double whose factory returns whatever get_pool says."""
    w3 = MagicMock()
    w3.eth.get_code.return_value = code

    factory_contract = MagicMock()
    factory_contract.functions.getPool.side_effect = (
        get_pool if get_pool else lambda *a: MagicMock(call=lambda: ZERO_ADDRESS)
    )
    token_contract = MagicMock()
    token_contract.functions.balanceOf.return_value.call.return_value = balance

    def contract(address=None, abi=None):
        names = [f.get("name") for f in abi]
        return factory_contract if "getPool" in names else token_contract

    w3.eth.contract.side_effect = contract
    return w3, factory_contract


def test_no_code_at_factory_raises_rather_than_reporting_no_pool():
    w3, _ = make_w3(code=b"")
    with pytest.raises(FactoryUnavailable, match="no contract code"):
        find_liquidity_pool(w3, TOKEN, FACTORY, QUOTE, (100, 500))


def test_no_code_at_quote_token_also_raises():
    w3, _ = make_w3()
    # Code at the factory, none at the quote token.
    w3.eth.get_code.side_effect = [b"\x60\x80", b""]
    with pytest.raises(FactoryUnavailable, match="quote token"):
        find_liquidity_pool(w3, TOKEN, FACTORY, QUOTE, (100, 500))


def test_every_probe_failing_raises_rather_than_reporting_no_pool():
    """All tiers reverting means a broken ABI or endpoint, not an
    absent pool."""
    def boom(*_args):
        raise ValueError("execution reverted")

    w3, _ = make_w3(get_pool=boom)
    with pytest.raises(FactoryUnavailable, match="looks wrong"):
        find_liquidity_pool(w3, TOKEN, FACTORY, QUOTE, (100, 500))


def test_factory_answering_zero_address_is_a_genuine_no_pool():
    w3, _ = make_w3()
    assert find_liquidity_pool(w3, TOKEN, FACTORY, QUOTE, (100, 500)) is None


def test_probes_exactly_the_fee_tiers_it_is_given():
    w3, factory = make_w3()
    find_liquidity_pool(w3, TOKEN, FACTORY, QUOTE, (100, 500, 2500, 10000))

    probed = [call.args[2] for call in factory.functions.getPool.call_args_list]
    assert probed == [100, 500, 2500, 10000]


def test_found_pool_reports_tier_address_and_balance():
    def get_pool(_token, _quote, fee):
        # Only the 0.25% Pancake tier has a pool.
        return MagicMock(call=lambda: POOL if fee == 2500 else ZERO_ADDRESS)

    w3, _ = make_w3(get_pool=get_pool, balance=42)
    pool = find_liquidity_pool(w3, TOKEN, FACTORY, QUOTE, (100, 500, 2500, 10000))

    assert pool is not None
    assert pool.fee_tier == 2500
    assert pool.pool_address == POOL
    assert pool.token_balance == 42


def test_uniswap_tiers_would_miss_a_pancake_only_pool():
    """Guards the reason BSC needs its own tier list."""
    def get_pool(_token, _quote, fee):
        return MagicMock(call=lambda: POOL if fee == 2500 else ZERO_ADDRESS)

    w3, _ = make_w3(get_pool=get_pool)
    assert find_liquidity_pool(w3, TOKEN, FACTORY, QUOTE, (100, 500, 3000, 10000)) is None
    assert find_liquidity_pool(w3, TOKEN, FACTORY, QUOTE, (100, 500, 2500, 10000)) is not None
