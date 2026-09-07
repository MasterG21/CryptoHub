"""Live execution: real routing, and a deliberate seam before real money moves.

What is implemented here: route discovery and quoting against the aggregators
that actually fill these trades — Jupiter on Solana, a 0x-compatible endpoint
on BNB Chain — including decimal handling, slippage limits, and turning the
aggregator's answer into a ``Fill``.

What is NOT implemented here: signing and broadcasting. That step needs a
private key, and this module has never been run against a mainnet RPC — the
development environment it was written in has no route to any of these hosts.
Shipping unexercised key-handling code that submits irreversible transactions
would be the single most dangerous thing in this repository, so instead the
final step is a ``TransactionSigner`` you supply and control.

To go live you must, deliberately and separately:

  1. set ``execution.mode = "live"`` and ``execution.allow_live_trading = true``
  2. pass a ``TransactionSigner`` implementation into ``LiveExecutor``
  3. verify the first fills by hand, at the smallest size the desk will accept

Two switches and an injected dependency, because no single typo should be able
to turn a simulation into real orders. Until step 2 is done, every order raises
``LiveTradingUnavailable`` — loudly, with nothing sent.
"""
from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable

import requests

from ..config import DeskConfig
from ..models import Chain, Fill, Order, Pair, Side
from .base import ExecutionError, SlippageExceeded

JUPITER_QUOTE_URL = "https://quote-api.jup.ag/v6/quote"
JUPITER_SWAP_URL = "https://quote-api.jup.ag/v6/swap"
ZEROX_BSC_URL = "https://bsc.api.0x.org/swap/v1/quote"

# The quote asset each chain's routes are priced against.
NATIVE_MINTS = {
    Chain.SOLANA: "So11111111111111111111111111111111111111112",  # wrapped SOL
    Chain.BNB: "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",  # WBNB
}


class LiveTradingUnavailable(ExecutionError):
    """Live mode was requested without everything it requires."""


@runtime_checkable
class TransactionSigner(Protocol):
    """Signs and broadcasts one prepared swap, returning a transaction id.

    The desk never sees a private key: it hands over an aggregator-built
    payload and gets back a reference. Implementations are responsible for key
    custody, simulating before sending, and priority fees.
    """

    def sign_and_send(self, chain: Chain, payload: dict[str, Any]) -> str:
        ...

    def wallet_address(self, chain: Chain) -> str:
        ...


class RouteQuote:
    """An aggregator's answer: what this order would actually fill at."""

    def __init__(
        self,
        chain: Chain,
        in_amount_raw: int,
        out_amount_raw: int,
        price_impact_pct: float,
        payload: dict[str, Any],
        route_label: str = "",
    ):
        self.chain = chain
        self.in_amount_raw = in_amount_raw
        self.out_amount_raw = out_amount_raw
        self.price_impact_pct = price_impact_pct
        self.payload = payload
        self.route_label = route_label


class LiveExecutor:
    """Routes orders through a DEX aggregator, then through your signer."""

    name = "live"

    def __init__(
        self,
        config: DeskConfig,
        signer: Optional[TransactionSigner] = None,
        session: Optional[requests.Session] = None,
        zerox_api_key: Optional[str] = None,
        timeout: float = 12.0,
    ):
        self.config = config
        self.signer = signer
        self.session = session or requests.Session()
        self.zerox_api_key = zerox_api_key
        self.timeout = timeout

    # ------------------------------------------------------------- preflight

    def preflight(self) -> list[str]:
        """Everything still standing between this desk and a live order."""
        blockers: list[str] = []
        if self.config.execution.mode != "live":
            blockers.append("execution.mode is not 'live'")
        if not self.config.execution.allow_live_trading:
            blockers.append("execution.allow_live_trading is false")
        if self.signer is None:
            blockers.append("no TransactionSigner supplied (see execution/live.py)")
        return blockers

    def _require_ready(self) -> None:
        blockers = self.preflight()
        if blockers:
            raise LiveTradingUnavailable(
                "live trading is not armed: " + "; ".join(blockers)
            )

    # ---------------------------------------------------------------- quoting

    def quote(self, order: Order, pair: Pair, decimals: int = 9) -> RouteQuote:
        """Ask the chain's aggregator what this order fills at.

        Quoting is safe and read-only, so it is callable without a signer —
        useful for checking real routable depth before arming anything.
        """
        if order.chain is Chain.SOLANA:
            return self._quote_jupiter(order, pair, decimals)
        if order.chain is Chain.BNB:
            return self._quote_zerox(order, pair, decimals)
        raise ExecutionError(
            f"no aggregator route configured for {order.chain.label}; "
            "trade it in paper mode or add a router here"
        )

    def _http_get(self, url: str, params: dict, headers: Optional[dict] = None) -> dict:
        try:
            resp = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
        except requests.RequestException as exc:
            raise ExecutionError(f"aggregator request failed: {exc}") from exc
        if resp.status_code >= 400:
            raise ExecutionError(f"aggregator returned {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    def _quote_jupiter(self, order: Order, pair: Pair, decimals: int) -> RouteQuote:
        native = NATIVE_MINTS[Chain.SOLANA]
        slippage_bps = int(order.max_slippage_pct * 10_000)
        if order.side is Side.BUY:
            sol_price = self._native_price_usd(pair, order)
            amount = int((order.usd_amount or 0) / sol_price * 10**9)
            input_mint, output_mint = native, order.token_address
        else:
            amount = int((order.quantity or 0) * 10**decimals)
            input_mint, output_mint = order.token_address, native
        if amount <= 0:
            raise ExecutionError("order amount rounds to zero at this token's decimals")

        data = self._http_get(
            JUPITER_QUOTE_URL,
            {
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": amount,
                "slippageBps": slippage_bps,
            },
        )
        impact = float(data.get("priceImpactPct") or 0.0)
        return RouteQuote(
            chain=Chain.SOLANA,
            in_amount_raw=int(data.get("inAmount") or amount),
            out_amount_raw=int(data.get("outAmount") or 0),
            price_impact_pct=impact,
            payload={"quoteResponse": data, "swap_url": JUPITER_SWAP_URL},
            route_label=data.get("routePlan", [{}])[0].get("swapInfo", {}).get("label", "jupiter"),
        )

    def _quote_zerox(self, order: Order, pair: Pair, decimals: int) -> RouteQuote:
        native = NATIVE_MINTS[Chain.BNB]
        headers = {"0x-api-key": self.zerox_api_key} if self.zerox_api_key else None
        if order.side is Side.BUY:
            bnb_price = self._native_price_usd(pair, order)
            params = {
                "sellToken": native,
                "buyToken": order.token_address,
                "sellAmount": int((order.usd_amount or 0) / bnb_price * 10**18),
                "slippagePercentage": order.max_slippage_pct,
            }
        else:
            params = {
                "sellToken": order.token_address,
                "buyToken": native,
                "sellAmount": int((order.quantity or 0) * 10**decimals),
                "slippagePercentage": order.max_slippage_pct,
            }
        if int(params["sellAmount"]) <= 0:
            raise ExecutionError("order amount rounds to zero at this token's decimals")

        data = self._http_get(ZEROX_BSC_URL, params, headers)
        impact_raw = data.get("estimatedPriceImpact")
        impact = float(impact_raw) / 100.0 if impact_raw not in (None, "") else 0.0
        return RouteQuote(
            chain=Chain.BNB,
            in_amount_raw=int(params["sellAmount"]),
            out_amount_raw=int(data.get("buyAmount") or 0),
            price_impact_pct=impact,
            payload={"transaction": data},
            route_label=(data.get("sources") or [{}])[0].get("name", "0x"),
        )

    def _native_price_usd(self, pair: Pair, order: Order) -> float:
        """USD price of the chain's native asset, needed to size a buy.

        Derived from the pair itself when it is quoted against the native
        asset. There is no fallback: guessing SOL at $150 when it is $220
        would silently size every order 45% wrong.
        """
        if pair.native_usd_price:
            return float(pair.native_usd_price)
        raise ExecutionError(
            f"USD price of {order.chain.native_symbol} is unknown; set "
            "pair.native_usd_price before sizing a live order"
        )

    # -------------------------------------------------------------- execution

    def execute(self, order: Order, pair: Optional[Pair] = None) -> Fill:
        self._require_ready()
        pair = pair or order.pair
        if pair is None:
            raise ExecutionError("live orders need the pair they are trading against")

        quote = self.quote(order, pair)
        if quote.price_impact_pct > order.max_slippage_pct:
            raise SlippageExceeded(quote.price_impact_pct, order.max_slippage_pct)

        assert self.signer is not None  # guaranteed by _require_ready
        payload = dict(quote.payload)
        payload["wallet"] = self.signer.wallet_address(order.chain)
        tx_ref = self.signer.sign_and_send(order.chain, payload)

        reference = order.reference_price or pair.price_usd or 0.0
        effective = reference * (
            1 + quote.price_impact_pct
            if order.side is Side.BUY
            else 1 - quote.price_impact_pct
        )
        # The signer reports what landed; until it is queried for the settled
        # amounts, the fill reflects the quote that was accepted.
        quantity = (
            (order.usd_amount or 0) / effective
            if order.side is Side.BUY
            else (order.quantity or 0)
        )
        gross = quantity * reference
        return Fill(
            order=order,
            quantity=quantity,
            price=effective,
            gross_usd=gross,
            fee_usd=gross * self.config.execution.dex_fee_pct,
            gas_usd=self.config.gas_for(order.chain),
            slippage_pct=quote.price_impact_pct,
            tx_ref=tx_ref,
        )
