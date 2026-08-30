"""Orchestrates the full check for one token, shared by single and batch modes."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from .analyzer import (
    HealthReport,
    build_report,
    score_age,
    score_deployer,
    score_holder_count,
    score_holders,
    score_liquidity,
    score_ownership,
    score_verification,
)
from .blockscout import BlockscoutClient
from .onchain import check_ownership, find_liquidity_pool, get_web3


@dataclass
class ScreenOptions:
    rpc_url: str
    v3_factory: Optional[str] = None
    weth: Optional[str] = None
    check_deployer: bool = True


def hours_since(iso_timestamp: str) -> Optional[float]:
    try:
        ts = iso_timestamp.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600
    except (ValueError, AttributeError):
        return None


def analyze_token(
    explorer: BlockscoutClient,
    address: str,
    opts: ScreenOptions,
    warn=lambda msg: None,
) -> HealthReport:
    """Run every check against one token. Raises only if the token itself
    can't be fetched; individual checks degrade to a warning + 'unknown'."""
    token = explorer.get_token(address)
    report = build_report(token)

    try:
        contract = explorer.get_smart_contract(address)
    except Exception as exc:
        warn(f"verification lookup failed: {exc}")
        contract = None
    score_verification(report, contract)

    try:
        holders = explorer.get_top_holders(address)
    except Exception as exc:
        warn(f"holder lookup failed: {exc}")
        holders = []
    score_holder_count(report, token.holder_count)

    lp_address = None
    liquidity_checked = False
    liquidity_found = False
    token_balance = None
    if opts.v3_factory and opts.weth:
        liquidity_checked = True
        try:
            w3 = get_web3(opts.rpc_url)
            pool = find_liquidity_pool(w3, address, opts.v3_factory, opts.weth)
            if pool:
                liquidity_found = True
                lp_address = pool.pool_address
                token_balance = pool.token_balance
        except Exception as exc:
            warn(f"liquidity check failed: {exc}")
            liquidity_checked = False
    score_liquidity(report, liquidity_checked, liquidity_found, token_balance)

    score_holders(report, holders, token.total_supply, lp_address)

    renounced = None
    try:
        ownership = check_ownership(get_web3(opts.rpc_url), address)
        if ownership.supported:
            renounced = ownership.renounced
    except Exception as exc:
        warn(f"ownership check failed: {exc}")
    score_ownership(report, renounced)

    hours_old = None
    try:
        created_at = explorer.get_creation_timestamp(address)
        if created_at:
            hours_old = hours_since(created_at)
    except Exception as exc:
        warn(f"creation-time lookup failed: {exc}")
    score_age(report, hours_old)

    if opts.check_deployer:
        deployer = None
        deployed_count = None
        try:
            deployer = explorer.get_deployer(address)
            if deployer:
                deployed_count = len(explorer.get_deployed_tokens(deployer))
        except Exception as exc:
            warn(f"deployer lookup failed: {exc}")
        score_deployer(report, deployer, deployed_count)

    return report
