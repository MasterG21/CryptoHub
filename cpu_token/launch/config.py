"""Launch configuration, read from a .env file and the environment.

The private key is read but never stored on the config object's repr,
never logged, and never written to any output file. Everything else is
printed back to you before anything is broadcast, because a launch you
cannot read back is a launch you cannot check.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

# Chain ids are the backstop against the single worst launch mistake:
# pointing at the wrong RPC and deploying somewhere you did not mean to.
NETWORKS = {
    "testnet": {"chain_id": 97, "name": "BNB Smart Chain Testnet",
                "explorer": "https://testnet.bscscan.com"},
    "mainnet": {"chain_id": 56, "name": "BNB Smart Chain",
                "explorer": "https://bscscan.com"},
}


class ConfigError(RuntimeError):
    pass


@dataclass
class LaunchConfig:
    network: str
    rpc_url: str
    treasury: str
    reward_token: Optional[str] = None
    distributor_owner: Optional[str] = None
    bscscan_api_key: Optional[str] = None
    bscscan_api_url: str = "https://api.etherscan.io/v2/api"
    _private_key: str = field(default="", repr=False)

    @property
    def chain_id(self) -> int:
        return NETWORKS[self.network]["chain_id"]

    @property
    def network_name(self) -> str:
        return NETWORKS[self.network]["name"]

    @property
    def explorer(self) -> str:
        return NETWORKS[self.network]["explorer"]

    @property
    def private_key(self) -> str:
        return self._private_key


def parse_env_file(path: str) -> dict:
    """Minimal KEY=VALUE reader, so there is no extra dependency."""
    values: dict[str, str] = {}
    if not os.path.exists(path):
        return values
    with open(path) as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            value = value.strip().strip('"').strip("'")
            # Strip trailing comments only when clearly separated, so a
            # value legitimately containing '#' survives.
            if " #" in value:
                value = value.split(" #", 1)[0].strip()
            values[key.strip()] = value
    return values


def load_config(env_path: str = ".env", overrides: Optional[dict] = None) -> LaunchConfig:
    values = {**parse_env_file(env_path), **os.environ, **(overrides or {})}

    network = (values.get("NETWORK") or "testnet").lower()
    if network not in NETWORKS:
        raise ConfigError(f"NETWORK must be one of {sorted(NETWORKS)}, got {network!r}")

    rpc_url = values.get("RPC_URL", "").strip()
    if not rpc_url:
        raise ConfigError("RPC_URL is not set. Copy config.example.env to .env and fill it in.")

    key = values.get("PRIVATE_KEY", "").strip()
    if key and not key.startswith("0x"):
        key = "0x" + key
    if key and len(key) != 66:
        raise ConfigError(
            "PRIVATE_KEY does not look like a 32-byte hex key. "
            "It should be 64 hex characters, optionally 0x-prefixed."
        )

    treasury = values.get("TREASURY_ADDRESS", "").strip()
    if not treasury:
        raise ConfigError(
            "TREASURY_ADDRESS is not set — this is the address that receives the "
            "entire CPU supply at deployment. Set it deliberately."
        )

    reward = values.get("REWARD_TOKEN_ADDRESS", "").strip() or None
    owner = values.get("DISTRIBUTOR_OWNER", "").strip() or None

    return LaunchConfig(
        network=network,
        rpc_url=rpc_url,
        treasury=treasury,
        reward_token=reward,
        distributor_owner=owner,
        bscscan_api_key=values.get("BSCSCAN_API_KEY", "").strip() or None,
        bscscan_api_url=(values.get("BSCSCAN_API_URL", "").strip()
                         or "https://api.etherscan.io/v2/api"),
        _private_key=key,
    )
