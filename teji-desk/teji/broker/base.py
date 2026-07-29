"""Abstractions the engine talks to: a market-data Feed and an Execution venue.

Concrete implementations: MockFeed / AngelOneFeed (data), PaperExecution /
AngelOneExecution (fills). The engine never imports a broker directly — it only
uses these interfaces, so swapping brokers is a one-file job.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional


# ---- market data --------------------------------------------------------
class Feed:
    """Pushes (price, cumulative_volume) into `on_tick` as the market moves."""

    def __init__(self, on_tick: Callable[[float, Optional[float]], None]):
        self.on_tick = on_tick

    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        pass


# ---- execution ----------------------------------------------------------
@dataclass
class Fill:
    price: float
    qty: int
    side: str        # BUY | SELL (the order side that executed)
    note: str = ""


class Execution:
    """Places (or simulates) orders and returns the fill."""

    is_live = False

    def market_order(self, side: str, qty: int, ltp: float) -> Fill:
        raise NotImplementedError
