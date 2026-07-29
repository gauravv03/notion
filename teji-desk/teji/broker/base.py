"""Abstractions the engine talks to: a market-data Feed and an Execution venue.

Feeds are multi-instrument: they push `(symbol, price, cumulative_volume)` so one
feed can serve a whole watchlist. The engine routes each tick to the matching
per-instrument Trader.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

# on_tick(symbol, price, cumulative_volume)
TickCb = Callable[[str, float, Optional[float]], None]


class Feed:
    def __init__(self, on_tick: TickCb):
        self.on_tick = on_tick

    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        pass


@dataclass
class Fill:
    price: float
    qty: float
    side: str        # BUY | SELL
    note: str = ""


class Execution:
    is_live = False

    def market_order(self, symbol: str, side: str, qty: float, ltp: float) -> Fill:
        raise NotImplementedError
