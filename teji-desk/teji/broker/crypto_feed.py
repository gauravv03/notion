"""Public crypto price feed (CoinDCX) — BTC/ETH in ₹, no account required.

CoinDCX publishes a free, unauthenticated ticker. We poll it and push last prices
for the configured markets (e.g. BTCINR, ETHINR). That means crypto works on REAL
live prices in paper mode with zero credentials.

Live crypto *orders* are a separate concern: they need an authenticated exchange
adapter (CoinDCX / Delta Exchange India) — see README. This module is data-only.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.request
from typing import List, Dict

from .base import Feed, TickCb

TICKER_URL = "https://api.coindcx.com/exchange/ticker"


class CryptoFeed(Feed):
    def __init__(self, on_tick: TickCb, instruments: List[Dict],
                 poll_seconds: float = 3.0, on_status=None):
        super().__init__(on_tick)
        self.poll = max(1.0, float(poll_seconds))
        self.on_status = on_status or (lambda s, n="": None)
        # market (e.g. BTCINR) -> internal symbol
        self.market_to_symbol = {inst["market"].upper(): inst["symbol"]
                                 for inst in instruments}
        self._stop = threading.Event()
        self._thread = None

    def _fetch(self):
        req = urllib.request.Request(TICKER_URL, headers={"User-Agent": "teji-desk"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.load(r)

    def _run(self):
        first = True
        while not self._stop.is_set():
            try:
                data = self._fetch()
                for row in data:
                    mkt = str(row.get("market", "")).upper()
                    sym = self.market_to_symbol.get(mkt)
                    if not sym:
                        continue
                    price = row.get("last_price")
                    if price is None:
                        continue
                    self.on_tick(sym, float(price), None)  # no cumulative volume -> VWAP falls back
                if first:
                    self.on_status("live", "coindcx ticker connected")
                    first = False
            except Exception as exc:
                self.on_status("error", f"crypto feed: {exc}")
            self._stop.wait(self.poll)

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
