"""Paper execution — simulates a market fill on the *live* price.

Real prices, real signals, real reasoning; only the fill is synthetic. A small
slippage is applied against you so paper results aren't rosier than reality.
"""
from __future__ import annotations

from .base import Execution, Fill


class PaperExecution(Execution):
    is_live = False

    def __init__(self, slippage_bps: float = 2.0):
        self.slippage = slippage_bps / 10_000.0

    def market_order(self, symbol: str, side: str, qty: float, ltp: float) -> Fill:
        price = ltp * (1 + self.slippage) if side == "BUY" else ltp * (1 - self.slippage)
        return Fill(price=price, qty=qty, side=side, note="paper fill")
