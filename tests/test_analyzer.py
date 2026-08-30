from robinhood_meme_scan.analyzer import (
    build_report,
    score_deployer,
    score_age,
    score_holder_count,
    score_holders,
    score_liquidity,
    score_ownership,
    score_verification,
)
from robinhood_meme_scan.blockscout import Holder, TokenInfo


def abi(views=(), writes=()):
    return (
        [{"type": "function", "name": n, "stateMutability": "view"} for n in views]
        + [{"type": "function", "name": n, "stateMutability": "nonpayable"} for n in writes]
    )


PLAIN_ERC20_ABI = abi(
    views=["name", "symbol", "decimals", "totalSupply", "balanceOf", "allowance"],
    writes=["transfer", "approve", "transferFrom"],
)


def make_token(**overrides):
    defaults = dict(
        address="0xToken",
        name="Doggy",
        symbol="DOGGY",
        decimals=18,
        total_supply=1_000_000,
        holder_count=500,
        is_verified=True,
    )
    defaults.update(overrides)
    return TokenInfo(**defaults)


def test_clean_token_scores_high():
    token = make_token()
    report = build_report(token)

    holders = [Holder(address=f"0x{i:040x}", balance=10_000) for i in range(20)]
    score_holders(report, holders, token.total_supply, lp_address=None)
    score_holder_count(report, token.holder_count)
    score_verification(report, {"abi": PLAIN_ERC20_ABI})
    score_ownership(report, renounced=True)
    score_liquidity(report, checked=True, found=True, token_balance=500_000)
    score_age(report, hours_old=24 * 30)

    assert report.score >= 80, report.flags
    assert report.verdict == "Looks healthy"


def test_unverified_contract_is_heavily_penalized():
    token = make_token(is_verified=False)
    report = build_report(token)
    score_verification(report, contract=None)

    assert report.score <= 70
    assert any(f.label == "unverified-contract" for f in report.flags)


def test_concentrated_holder_flags_top1_and_top10():
    token = make_token(total_supply=1000)
    report = build_report(token)
    holders = [
        Holder(address="0xwhale", balance=300),
        *[Holder(address=f"0xsmall{i}", balance=10) for i in range(9)],
    ]
    score_holders(report, holders, token.total_supply, lp_address=None)

    assert report.holder_top1_pct == 30.0
    labels = [f.label for f in report.flags]
    assert "holder-concentration" in labels


def test_lp_address_excluded_from_holder_math():
    token = make_token(total_supply=1000)
    report = build_report(token)
    holders = [
        Holder(address="0xlppool", balance=600),
        Holder(address="0xreal", balance=100),
    ]
    score_holders(report, holders, token.total_supply, lp_address="0xLPPool")

    assert report.holder_top1_pct == 10.0


def test_low_holder_count_flag():
    token = make_token(holder_count=5)
    report = build_report(token)
    score_holder_count(report, token.holder_count)

    assert any(f.label == "low-holder-count" for f in report.flags)


def test_no_liquidity_pool_flag():
    token = make_token()
    report = build_report(token)
    score_liquidity(report, checked=True, found=False)

    assert report.liquidity_checked is True
    assert any(f.label == "no-liquidity-pool" for f in report.flags)


def test_liquidity_not_checked_raises_no_flag():
    token = make_token()
    report = build_report(token)
    score_liquidity(report, checked=False, found=False)

    assert not report.flags


def test_owner_not_renounced_flag():
    token = make_token()
    report = build_report(token)
    score_ownership(report, renounced=False)

    assert any(f.label == "owner-not-renounced" for f in report.flags)


def test_score_never_goes_below_zero_or_above_hundred():
    token = make_token()
    report = build_report(token)
    for _ in range(20):
        score_ownership(report, renounced=False)

    assert report.score == 0

    report2 = build_report(token)
    assert report2.score == 100


def test_dangerous_abi_functions_detected():
    report = build_report(make_token())
    score_verification(report, {"abi": abi(
        views=["name", "owner"],
        writes=["mint", "setBlacklist", "pause", "transferOwnership"],
    )})

    labels = [f.label for f in report.flags]
    assert "owner-can-mint-new-supply" in labels
    assert "can-blacklist-wallets" in labels
    assert "trading-can-be-paused" in labels
    assert report.score <= 40


def test_plain_erc20_source_patterns_no_longer_false_positive():
    """A normal fixed-supply ERC20 calls _mint() in its constructor and
    contains 'onlyOwner' in its imports. Neither is exposed as a callable
    function, so neither should be flagged."""
    report = build_report(make_token())
    score_verification(report, {"abi": PLAIN_ERC20_ABI})

    assert report.flags == []
    assert report.score == 100


def test_view_only_function_is_not_treated_as_dangerous():
    report = build_report(make_token())
    score_verification(report, {"abi": abi(views=["mint"], writes=["transfer"])})

    assert report.score == 100


def test_verified_without_abi_is_not_scanned_by_source():
    report = build_report(make_token())
    score_verification(report, {"source_code": "contract X { function mint() {} }"})

    labels = [f.label for f in report.flags]
    assert labels == ["abi-unavailable"]


def test_factory_deployer_is_not_penalised():
    """Every token on a launchpad is created by the platform's factory."""
    report = build_report(make_token())
    score_deployer(report, "0xfactory", 50, deployer_is_factory=True)

    assert report.flags == []
    assert report.deployer_is_factory is True


def test_human_wallet_with_many_launches_is_flagged():
    report = build_report(make_token())
    score_deployer(report, "0xwallet", 50, deployer_is_factory=False)

    assert any(f.label == "serial-deployer" for f in report.flags)
    assert "50+" in report.flags[0].detail
