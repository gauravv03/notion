"""Synthetic feed so the whole pipeline runs offline / after market hours.

It generates a believable intraday tape (trend + noise + volume) so you can watch
real crossovers, real reasoning and real (paper) fills end-to-end before wiring
Angel One. This is the ONLY place numbers are invented, and it's clearly labelled
`feed: mock` everywhere in the UI.
"""
from __future__ import annotations

import random
import threading
import time
from typing import Callable, Optional

from .base import Feed


class MockFeed(Feed):
    def __init__(self, on_tick: Callable[[float, Optional[float]], None],
                 start_price: float = 24500.0, ticks_per_sec: float = 4.0):
        super().__init__(on_tick)
        self.price = start_price
        self.cum_volume = 0.0
        self.dt = 1.0 / ticks_per_sec
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        # a persistent drift that occasionally flips, so clean trends form
        # (mock only — real feeds bring their own reality)
        self._drift = random.choice([-1, 1]) * random.uniform(0.00010, 0.00022)

    def _run(self):
        while not self._stop.is_set():
            if random.random() < 0.004:  # rarely flip regime -> long, readable trends
                self._drift = random.choice([-1, 1]) * random.uniform(0.00010, 0.00022)
            shock = random.gauss(0, 0.00035)
            self.price *= (1 + self._drift + shock)
            self.cum_volume += random.randint(20, 260)
            try:
                self.on_tick(self.price, self.cum_volume)
            except Exception as exc:  # a bad tick must never kill the feed
                print("[mockfeed] on_tick error:", exc)
            time.sleep(self.dt)

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
