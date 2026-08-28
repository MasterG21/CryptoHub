"""Thin client over Blockscout's v2 REST API for Robinhood Chain."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import requests

DEFAULT_EXPLORER_API = "https://robinhoodchain.blockscout.com/api/v2"
BURN_ADDRESSES = {
    "0x0000000000000000000000000000000000000000",
    "0x000000000000000000000000000000000000dead",
}


class BlockscoutError(RuntimeError):
    """Raised when the explorer API can't answer a required question."""


@dataclass
class Holder:
    address: str
    balance: int


@dataclass
class TokenInfo:
    address: str
    name: Optional[str]
    symbol: Optional[str]
    decimals: int
    total_supply: int
    holder_count: Optional[int]
    is_verified: Optional[bool]
    raw: dict = field(default_factory=dict, repr=False)


class BlockscoutClient:
    """Wraps the handful of Blockscout v2 endpoints the analyzer needs.

    Field names vary slightly across Blockscout deployments/versions, so
    every accessor here tries a few known key spellings and returns None
    (rather than raising) when a value truly isn't available, so callers
    can surface "unknown" instead of a wrong guess.
    """

    def __init__(self, base_url: str = DEFAULT_EXPLORER_API, timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def _get(self, path: str, params: Optional[dict] = None) -> Any:
        url = f"{self.base_url}{path}"
        resp = self.session.get(url, params=params, timeout=self.timeout)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def get_token(self, address: str) -> TokenInfo:
        data = self._get(f"/tokens/{address}")
        if data is None:
            raise BlockscoutError(f"Token {address} not found on this explorer")

        decimals_raw = data.get("decimals")
        try:
            decimals = int(decimals_raw) if decimals_raw is not None else 18
        except (TypeError, ValueError):
            decimals = 18

        total_supply_raw = data.get("total_supply")
        try:
            total_supply = int(total_supply_raw) if total_supply_raw is not None else 0
        except (TypeError, ValueError):
            total_supply = 0

        holder_count = data.get("holders_count", data.get("holders"))
        try:
            holder_count = int(holder_count) if holder_count is not None else None
        except (TypeError, ValueError):
            holder_count = None

        is_verified = None
        for key in ("is_verified", "verified"):
            if key in data:
                is_verified = bool(data[key])
                break

        return TokenInfo(
            address=address,
            name=data.get("name"),
            symbol=data.get("symbol"),
            decimals=decimals,
            total_supply=total_supply,
            holder_count=holder_count,
            is_verified=is_verified,
            raw=data,
        )

    def get_top_holders(self, address: str, limit: int = 25) -> list[Holder]:
        data = self._get(f"/tokens/{address}/holders")
        if not data:
            return []
        items = data.get("items", data if isinstance(data, list) else [])
        holders: list[Holder] = []
        for item in items[:limit]:
            addr = item.get("address")
            addr_hash = None
            if isinstance(addr, dict):
                addr_hash = addr.get("hash")
            elif isinstance(addr, str):
                addr_hash = addr
            value = item.get("value", item.get("balance"))
            if addr_hash is None or value is None:
                continue
            try:
                balance = int(value)
            except (TypeError, ValueError):
                continue
            holders.append(Holder(address=addr_hash.lower(), balance=balance))
        return holders

    def get_smart_contract(self, address: str) -> Optional[dict]:
        """Returns verification/source info, or None if unverified/unknown."""
        return self._get(f"/smart-contracts/{address}")

    def get_address_info(self, address: str) -> Optional[dict]:
        return self._get(f"/addresses/{address}")

    def get_transaction(self, tx_hash: str) -> Optional[dict]:
        return self._get(f"/transactions/{tx_hash}")

    def get_creation_timestamp(self, token_address: str) -> Optional[str]:
        """Best-effort lookup of the ISO timestamp the token contract was created."""
        addr_info = self.get_address_info(token_address)
        if not addr_info:
            return None
        tx_hash = None
        for key in ("creation_tx_hash", "creation_transaction_hash"):
            if addr_info.get(key):
                tx_hash = addr_info[key]
                break
        if not tx_hash:
            return None
        tx = self.get_transaction(tx_hash)
        if not tx:
            return None
        return tx.get("timestamp")
