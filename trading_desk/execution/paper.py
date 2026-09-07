"""Paper execution: simulated fills that charge every real cost.

The point of this engine is not to show what the strategy could earn under
ideal conditions — it is to be pessimistic enough that a result here means
something. Every fill pays price impact from the pool's own depth, the DEX
fee, and chain gas. Optionally it also fails outright some of the time, which
is what actually happens to a slow transaction on a moving memecoin.
"""
from __future__ import annotations

import random
from typing import Optional

from ..config import DeskConfig
from ..models import Fill, Order, Pair, Side
from .base import ExecutionError, SlippageExceeded, buy_impact_pct, sell_impact_pct


class PaperExecutor:
    name = "paper"

    def __init__(
        self,
        config: DeskConfig,
        failure_rate: float = 0.0,
        rng: Optional[random.Random] = None,
    ):
        self.config = config
        self.failure_rate = failure_rate
        self.rng = rng or random.Random()
        self.fills: list[Fill] = []

    def execute(self, order: Order, pair: Optional[Pair] = None) -> Fill:
        pair = pair or order.pair
        reference = order.reference_price or (pair.price_usd if pair else None)
        if not reference or reference <= 0:
            raise ExecutionError("no reference price to fill against")
        liquidity = pair.liquidity_usd if pair else None
        if liquidity is None:
            raise ExecutionError("pool liquidity unknown; refusing to simulate a fill")

        if self.failure_rate and self.rng.random() < self.failure_rate:
            raise ExecutionError("transaction failed or was front-run before landing")

        gas = self.config.gas_for(order.chain)
        fee_pct = self.config.execution.dex_fee_pct

        if order.side is Side.BUY:
            fill = self._buy(order, reference, liquidity, fee_pct, gas)
        else:
            fill = self._sell(order, reference, liquidity, fee_pct, gas)
        self.fills.append(fill)
        return fill

    def _buy(
        self, order: Order, reference: float, liquidity: float, fee_pct: float, gas: float
    ) -> Fill:
        usd = order.usd_amount
        if not usd or usd <= 0:
            raise ExecutionError("buy order has no USD amount")

        impact = buy_impact_pct(usd, liquidity)
        if impact > order.max_slippage_pct:
            raise SlippageExceeded(impact, order.max_slippage_pct)

        effective_price = reference * (1 + impact)
        fee = usd * fee_pct
        spent_on_tokens = usd - fee
        quantity = spent_on_tokens / effective_price
        return Fill(
            order=order,
            quantity=quantity,
            price=effective_price,
            gross_usd=quantity * reference,
            fee_usd=fee,
            gas_usd=gas,
            slippage_pct=impact,
            tx_ref="paper",
        )

    def _sell(
        self, order: Order, reference: float, liquidity: float, fee_pct: float, gas: float
    ) -> Fill:
        quantity = order.quantity
        if not quantity or quantity <= 0:
            raise ExecutionError("sell order has no quantity")

        notional = quantity * reference
        impact = sell_impact_pct(notional, liquidity)
        if impact > order.max_slippage_pct:
            raise SlippageExceeded(impact, order.max_slippage_pct)

        effective_price = reference * (1 - impact)
        gross = quantity * effective_price
        return Fill(
            order=order,
            quantity=quantity,
            price=effective_price,
            gross_usd=quantity * reference,
            fee_usd=gross * fee_pct,
            gas_usd=gas,
            slippage_pct=impact,
            tx_ref="paper",
        )
