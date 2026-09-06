"""Chain presets: lookup, aliases, and the per-DEX details that differ."""
import pytest

from robinhood_meme_scan.chains import (
    BSC,
    CHAINS,
    DEFAULT_CHAIN,
    PANCAKESWAP_V3_FEE_TIERS,
    ROBINHOOD,
    UNISWAP_V3_FEE_TIERS,
    get_chain,
)


def test_default_chain_is_robinhood_so_existing_usage_is_unchanged():
    assert DEFAULT_CHAIN == "robinhood"
    assert get_chain(DEFAULT_CHAIN) is ROBINHOOD


@pytest.mark.parametrize("alias", ["bsc", "bnb", "BNB", "binance", " bnbchain "])
def test_bsc_aliases_all_resolve(alias):
    assert get_chain(alias) is BSC


def test_unknown_chain_names_the_known_ones():
    with pytest.raises(KeyError) as exc:
        get_chain("solana")
    assert "bsc" in str(exc.value)


def test_pancakeswap_fee_tiers_differ_from_uniswap():
    """PancakeSwap V3's third tier is 0.25%, not Uniswap's 0.3%. Probing
    Uniswap's tiers on BSC would miss most real pools and report them as
    having no liquidity."""
    assert 2500 in PANCAKESWAP_V3_FEE_TIERS
    assert 3000 not in PANCAKESWAP_V3_FEE_TIERS
    assert 3000 in UNISWAP_V3_FEE_TIERS
    assert BSC.v3_fee_tiers == PANCAKESWAP_V3_FEE_TIERS


def test_bsc_has_liquidity_configured_and_robinhood_does_not():
    assert BSC.liquidity_configured
    assert BSC.quote_symbol == "WBNB"
    # Robinhood Chain's factory/WETH addresses are unconfirmed, so the
    # check stays opt-in there rather than guessing.
    assert not ROBINHOOD.liquidity_configured


def test_every_preset_has_an_explorer_and_rpc():
    for chain in CHAINS.values():
        assert chain.explorer_api.startswith("https://")
        assert chain.rpc_url.startswith("https://")
        assert chain.explorer_url.startswith("https://")
