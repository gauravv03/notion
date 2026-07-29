"""Synthetic multi-instrument feed so the whole desk runs offline / after hours.

Each instrument gets its own believable random walk (trend + noise + volume) so
you can watch real crossovers, real reasoning and real (paper) fills across the
whole watchlist before wiring any broker. This is the ONLY place prices are
invented, and it's labelled `mock` everywhere in the UI.
"""
from __future__ import annotations

import random
import threading
import time
from typing import List, Dict

from .base import Feed, TickCb


class MockFeed(Feed):
    def __init__(self, on_tick: TickCb, instruments: List[Dict], ticks_per_sec: float = 4.0):
        super().__init__(on_tick)
        self.dt = 1.0 / ticks_per_sec
        self._stop = threading.Event()
        self._thread = None
        self.books = []
        for inst in instruments:
            start = float(inst.get("ref_price") or 1000.0)
            self.books.append({
                "symbol": inst["symbol"],
                "price": start,
                "cum_volume": 0.0,
                "drift": random.choice([-1, 1]) * random.uniform(0.00010, 0.00022),
            })

    def _run(self):
        while not self._stop.is_set():
            for b in self.books:
                if random.random() < 0.004:
                    b["drift"] = random.choice([-1, 1]) * random.uniform(0.00010, 0.00022)
                b["price"] *= (1 + b["drift"] + random.gauss(0, 0.00035))
                b["cum_volume"] += random.randint(20, 260)
                try:
                    self.on_tick(b["symbol"], b["price"], b["cum_volume"])
                except Exception as exc:
                    print("[mockfeed] on_tick error:", exc)
            time.sleep(self.dt)

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
