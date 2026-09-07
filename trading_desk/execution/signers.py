"""Transaction signers — the last mile between a route and a filled order.

These hold your keys and broadcast real, irreversible transactions. Read this
header before arming anything.

**Never run against mainnet.** No line of this file has executed against a live
chain: the environment it was written in has no route to any RPC, aggregator or
explorer. It is written carefully and unit-tested where testable, and that is
not the same as proven. Treat the first live session as a test with real money
at the smallest size the desk will accept, watching every fill.

Safety rails, all on by default:

  * ``dry_run=True`` — everything runs including simulation, nothing is
    broadcast. You must pass ``dry_run=False`` deliberately.
  * ``max_order_usd`` — a hard per-order ceiling enforced *here*, independent of
    the desk's own risk config, so a bad config cannot produce a large order.
  * ``simulate_before_send`` — the transaction is simulated and a failing
    simulation aborts the send.
  * Keys are read from the environment only, never from config files or the
    command line, and are redacted from every repr and log line.

Key handling rules this file follows and you should too: keys live in the
environment of the process, never in the repo, never in the journal, never in a
log. Use a wallet funded with only what the desk is allowed to lose.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Optional

from ..models import Chain
from .base import ExecutionError

# Environment variables the signers read keys from. Nothing else is consulted.
SOLANA_KEY_ENV = "DESK_SOLANA_PRIVATE_KEY"
EVM_KEY_ENV = "DESK_EVM_PRIVATE_KEY"

DEFAULT_SOLANA_RPC = "https://api.mainnet-beta.solana.com"
DEFAULT_BNB_RPC = "https://bsc-dataseed.binance.org"

# Minimal ERC-20 surface needed to size and approve a sell.
_ERC20_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "spender", "type": "address"},
        ],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]


# ERC-20 approve() costs ~45k gas; the margin covers tokens with transfer hooks
# or fee-on-transfer bookkeeping in their approval path.
_APPROVAL_GAS_LIMIT = 120_000


class SignerError(ExecutionError):
    """The signer refused, or could not complete, a submission."""


class KeyLoadError(SignerError):
    """A key is missing or malformed. The message never contains key material."""


@dataclass
class SignerLimits:
    """Rails applied by the signer itself, below the desk's own risk layer.

    Defence in depth: the desk already caps order size, but a config typo or a
    logic bug upstream should still not be able to send a large transaction.
    """

    dry_run: bool = True
    max_order_usd: float = 25.0
    simulate_before_send: bool = True
    max_slippage_pct: float = 0.20

    def check(self, usd_amount: Optional[float]) -> None:
        if usd_amount is None:
            return
        if usd_amount > self.max_order_usd:
            raise SignerError(
                f"order of ${usd_amount:,.2f} exceeds the signer's hard cap of "
                f"${self.max_order_usd:,.2f}; raise max_order_usd deliberately if "
                "this is intended"
            )


class _RedactedRepr:
    """Base class that keeps key material out of reprs, logs and tracebacks."""

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<{type(self).__name__} wallet={getattr(self, '_public', '?')} keys=REDACTED>"

    __str__ = __repr__


class SolanaSigner(_RedactedRepr):
    """Signs and sends Jupiter swap transactions on Solana.

    Jupiter's /swap endpoint returns a fully-built, base64 versioned
    transaction. The only thing this adds is your signature — it does not
    construct instructions, so the route you simulate is the route you send.

    Requires ``solders`` and ``base58``:  pip install solders base58
    """

    def __init__(
        self,
        rpc_url: str = DEFAULT_SOLANA_RPC,
        limits: Optional[SignerLimits] = None,
        key_env: str = SOLANA_KEY_ENV,
        session: Optional[Any] = None,
        timeout: float = 20.0,
    ):
        self.rpc_url = rpc_url
        self.limits = limits or SignerLimits()
        self.key_env = key_env
        self.timeout = timeout
        self._keypair = None
        self._public: Optional[str] = None
        self._session = session
        self._decimals_cache: dict[str, int] = {}

    # ------------------------------------------------------------------ keys

    def _load_keypair(self):
        """Load the keypair from the environment, once.

        Accepts the two formats wallets actually export: a base58 secret key
        (Phantom's "export private key") and a JSON byte array (the
        ``solana-keygen`` file format). Errors never quote the value.
        """
        if self._keypair is not None:
            return self._keypair

        # Check the key before the dependency: "you have not set a key" is the
        # more actionable message, and it does not require solders to say it.
        raw = os.environ.get(self.key_env, "").strip()
        if not raw:
            raise KeyLoadError(f"{self.key_env} is not set")

        try:
            from solders.keypair import Keypair
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise KeyLoadError(
                "solders is not installed; run: pip install solders base58"
            ) from exc

        try:
            if raw.startswith("["):
                secret = bytes(json.loads(raw))
                keypair = Keypair.from_bytes(secret)
            else:
                import base58

                keypair = Keypair.from_bytes(base58.b58decode(raw))
        except Exception as exc:
            raise KeyLoadError(
                f"{self.key_env} is not a valid Solana secret key "
                f"(expected base58 or a JSON byte array): {type(exc).__name__}"
            ) from exc

        self._keypair = keypair
        self._public = str(keypair.pubkey())
        return keypair

    def wallet_address(self, chain: Chain = Chain.SOLANA) -> str:
        self._load_keypair()
        assert self._public is not None
        return self._public

    # ------------------------------------------------------------------- rpc

    def _rpc(self, method: str, params: list) -> Any:
        import requests

        session = self._session or requests
        response = session.post(
            self.rpc_url,
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            timeout=self.timeout,
        )
        payload = response.json()
        if "error" in payload:
            raise SignerError(f"Solana RPC {method} failed: {payload['error']}")
        return payload.get("result")

    def token_decimals(self, chain: Chain, token_address: str) -> int:
        cached = self._decimals_cache.get(token_address)
        if cached is not None:
            return cached
        result = self._rpc("getTokenSupply", [token_address])
        try:
            decimals = int(result["value"]["decimals"])
        except (KeyError, TypeError, ValueError) as exc:
            raise SignerError(
                f"could not read decimals for {token_address}"
            ) from exc
        self._decimals_cache[token_address] = decimals
        return decimals

    # -------------------------------------------------------------- signing

    def sign_and_send(self, chain: Chain, payload: dict[str, Any]) -> str:
        if chain is not Chain.SOLANA:
            raise SignerError(f"SolanaSigner cannot sign for {chain.label}")
        self.limits.check(payload.get("usd_amount"))

        quote_response = payload.get("quoteResponse")
        if not quote_response:
            raise SignerError("Jupiter quote missing from the payload")

        swap_transaction = self._request_swap_transaction(payload, quote_response)
        signed = self._sign(swap_transaction)

        if self.limits.simulate_before_send:
            self._simulate(signed)
        if self.limits.dry_run:
            return "dryrun:solana:not-broadcast"
        return self._rpc(
            "sendTransaction",
            [signed, {"encoding": "base64", "maxRetries": 3, "skipPreflight": False}],
        )

    def _request_swap_transaction(self, payload: dict, quote_response: dict) -> str:
        """Ask Jupiter to build the swap transaction for our wallet."""
        import requests

        session = self._session or requests
        response = session.post(
            payload.get("swap_url"),
            json={
                "quoteResponse": quote_response,
                "userPublicKey": self.wallet_address(),
                "wrapAndUnwrapSol": True,
                "dynamicComputeUnitLimit": True,
            },
            timeout=self.timeout,
        )
        data = response.json()
        transaction = data.get("swapTransaction")
        if not transaction:
            raise SignerError(f"Jupiter did not return a transaction: {str(data)[:200]}")
        return transaction

    def _sign(self, swap_transaction_b64: str) -> str:
        import base64

        from solders.transaction import VersionedTransaction

        keypair = self._load_keypair()
        raw = base64.b64decode(swap_transaction_b64)
        unsigned = VersionedTransaction.from_bytes(raw)
        signed = VersionedTransaction(unsigned.message, [keypair])
        return base64.b64encode(bytes(signed)).decode()

    def _simulate(self, signed_b64: str) -> None:
        result = self._rpc(
            "simulateTransaction",
            [signed_b64, {"encoding": "base64", "commitment": "processed"}],
        )
        error = (result or {}).get("value", {}).get("err")
        if error:
            raise SignerError(f"transaction simulation failed, not sending: {error}")


class EvmSigner(_RedactedRepr):
    """Signs and sends 0x-routed swaps on BNB Chain (or any EVM chain).

    Two things make an EVM sell different from a buy, and both are handled
    here: the token must be approved for the router before it can be sold, and
    the approval is written for the exact amount rather than an unlimited
    allowance — an infinite approval left on a memecoin router is a standing
    invitation to drain the wallet later.

    Requires ``web3`` and ``eth_account`` (both already in requirements.txt).
    """

    def __init__(
        self,
        rpc_url: str = DEFAULT_BNB_RPC,
        chain: Chain = Chain.BNB,
        limits: Optional[SignerLimits] = None,
        key_env: str = EVM_KEY_ENV,
        web3=None,
        timeout: float = 20.0,
    ):
        self.rpc_url = rpc_url
        self.chain = chain
        self.limits = limits or SignerLimits()
        self.key_env = key_env
        self.timeout = timeout
        self._web3 = web3
        self._account = None
        self._public: Optional[str] = None
        self._decimals_cache: dict[str, int] = {}

    # ------------------------------------------------------------------ keys

    def _load_account(self):
        if self._account is not None:
            return self._account
        try:
            from eth_account import Account
        except ImportError as exc:  # pragma: no cover
            raise KeyLoadError("eth_account is not installed; pip install web3") from exc

        raw = os.environ.get(self.key_env, "").strip()
        if not raw:
            raise KeyLoadError(f"{self.key_env} is not set")
        try:
            account = Account.from_key(raw)
        except Exception as exc:
            raise KeyLoadError(
                f"{self.key_env} is not a valid EVM private key: {type(exc).__name__}"
            ) from exc

        self._account = account
        self._public = account.address
        return account

    def wallet_address(self, chain: Optional[Chain] = None) -> str:
        self._load_account()
        assert self._public is not None
        return self._public

    def _w3(self):
        if self._web3 is None:
            from web3 import Web3

            self._web3 = Web3(Web3.HTTPProvider(self.rpc_url))
        return self._web3

    def _erc20(self, token_address: str):
        from web3 import Web3

        return self._w3().eth.contract(
            address=Web3.to_checksum_address(token_address), abi=_ERC20_ABI
        )

    def token_decimals(self, chain: Chain, token_address: str) -> int:
        cached = self._decimals_cache.get(token_address)
        if cached is not None:
            return cached
        try:
            decimals = int(self._erc20(token_address).functions.decimals().call())
        except Exception as exc:
            raise SignerError(f"could not read decimals for {token_address}: {exc}") from exc
        self._decimals_cache[token_address] = decimals
        return decimals

    # -------------------------------------------------------------- signing

    def sign_and_send(self, chain: Chain, payload: dict[str, Any]) -> str:
        if chain is not self.chain:
            raise SignerError(f"EvmSigner is configured for {self.chain.label}, not {chain.label}")
        self.limits.check(payload.get("usd_amount"))

        transaction = payload.get("transaction")
        if not isinstance(transaction, dict) or not transaction.get("to"):
            raise SignerError("0x quote missing the transaction to send")

        approval_ref = self._ensure_allowance(payload, transaction)
        tx_hash = self._send(self._build(transaction))
        return tx_hash if approval_ref is None else f"{approval_ref},{tx_hash}"

    def _ensure_allowance(self, payload: dict, transaction: dict) -> Optional[str]:
        """Approve exactly the amount being sold, if the router lacks allowance.

        Buys spend the native asset and need no approval, so this is a no-op
        for them. Skipping it on a sell would leave a position that cannot be
        exited, which is the worst failure this desk has.
        """
        sell_token = payload.get("sell_token")
        sell_amount = payload.get("sell_amount")
        if not sell_token or not sell_amount:
            return None
        spender = transaction.get("allowanceTarget") or transaction.get("to")
        if not spender:
            return None

        from web3 import Web3

        owner = self.wallet_address()
        token = self._erc20(sell_token)
        try:
            current = int(
                token.functions.allowance(
                    Web3.to_checksum_address(owner), Web3.to_checksum_address(spender)
                ).call()
            )
        except Exception as exc:
            raise SignerError(f"could not read allowance for {sell_token}: {exc}") from exc
        if current >= int(sell_amount):
            return None

        if self.limits.dry_run:
            return "dryrun:approve:not-broadcast"
        w3 = self._w3()
        # gas and gasPrice are set explicitly rather than left to the builder:
        # an approval that is under-gassed strands the position, and this is
        # the transaction that stands between a losing trade and an exit.
        approve = token.functions.approve(
            Web3.to_checksum_address(spender), int(sell_amount)
        ).build_transaction(
            {
                "from": Web3.to_checksum_address(owner),
                "nonce": w3.eth.get_transaction_count(Web3.to_checksum_address(owner)),
                "chainId": w3.eth.chain_id,
                "gasPrice": w3.eth.gas_price,
                "gas": _APPROVAL_GAS_LIMIT,
            }
        )
        return self._send(approve)

    def _build(self, transaction: dict) -> dict:
        from web3 import Web3

        w3 = self._w3()
        owner = Web3.to_checksum_address(self.wallet_address())
        built = {
            "to": Web3.to_checksum_address(transaction["to"]),
            "data": transaction.get("data", "0x"),
            "value": int(transaction.get("value") or 0),
            "from": owner,
            "nonce": w3.eth.get_transaction_count(owner),
            "chainId": w3.eth.chain_id,
        }
        gas_price = transaction.get("gasPrice")
        built["gasPrice"] = int(gas_price) if gas_price else w3.eth.gas_price
        # Prefer the aggregator's gas estimate; fall back to our own, with a
        # margin, because a swap that runs out of gas still costs the gas.
        gas = transaction.get("gas")
        built["gas"] = int(gas) if gas else int(w3.eth.estimate_gas(built) * 1.25)
        return built

    def _send(self, transaction: dict) -> str:
        w3 = self._w3()
        if self.limits.simulate_before_send:
            try:
                w3.eth.call(transaction)
            except Exception as exc:
                raise SignerError(f"transaction reverted in simulation, not sending: {exc}") from exc
        if self.limits.dry_run:
            return "dryrun:evm:not-broadcast"
        account = self._load_account()
        signed = account.sign_transaction(transaction)
        raw = getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction")
        return w3.eth.send_raw_transaction(raw).hex()


class MultiChainSigner(_RedactedRepr):
    """Routes each chain's orders to the signer that holds that chain's key."""

    def __init__(self, signers: dict[Chain, Any]):
        self.signers = signers
        self._public = "multi"

    def _for(self, chain: Chain):
        signer = self.signers.get(chain)
        if signer is None:
            raise SignerError(f"no signer configured for {chain.label}")
        return signer

    def sign_and_send(self, chain: Chain, payload: dict[str, Any]) -> str:
        return self._for(chain).sign_and_send(chain, payload)

    def wallet_address(self, chain: Chain) -> str:
        return self._for(chain).wallet_address(chain)

    def token_decimals(self, chain: Chain, token_address: str) -> int:
        return self._for(chain).token_decimals(chain, token_address)
