"""Angel One SmartAPI adapter: multi-instrument live feed + (gated) live orders.

Login uses your PIN + a TOTP derived from ANGEL_TOTP_SECRET. The feed subscribes
to every equity/index/F&O instrument's token over SmartWebSocketV2 and routes each
tick to its symbol. Live orders are placed with `placeOrder` and are ONLY reachable
when config `mode: live`.

NOTE: SmartAPI response field names shift across SDK versions. Parsing is defensive
and the first tick's keys are printed so you can confirm them on a new SDK.
"""
from __future__ import annotations

import threading
from collections import defaultdict
from typing import Dict, List, Optional

import pyotp

from .base import Feed, Execution, Fill, TickCb

_PAISE = 100.0


def _login(creds):
    from SmartApi import SmartConnect
    obj = SmartConnect(api_key=creds.api_key)
    totp = pyotp.TOTP(creds.totp_secret).now()
    session = obj.generateSession(creds.client_code, creds.pin, totp)
    if not session or not session.get("status", False):
        raise RuntimeError(f"Angel One login failed: {session}")
    return obj, session["data"]["jwtToken"], obj.getfeedToken()


class AngelOneFeed(Feed):
    def __init__(self, on_tick: TickCb, creds, instruments: List[Dict], on_status=None):
        super().__init__(on_tick)
        self.creds = creds
        self.instruments = instruments
        self.on_status = on_status or (lambda s, n="": None)
        self.token_to_symbol = {str(i["token"]): i["symbol"] for i in instruments}
        # group tokens by exchangeType for a single subscribe call
        self.by_exch = defaultdict(list)
        for i in instruments:
            self.by_exch[int(i.get("exchange_type", 1))].append(str(i["token"]))
        self._sws = None
        self._thread = None
        self._debugged = False

    def start(self):
        from SmartApi.smartWebSocketV2 import SmartWebSocketV2
        obj, auth_token, feed_token = _login(self.creds)
        sws = SmartWebSocketV2(auth_token, self.creds.api_key,
                               self.creds.client_code, feed_token)
        self._sws = sws
        token_list = [{"exchangeType": et, "tokens": toks} for et, toks in self.by_exch.items()]

        def on_open(wsapp):
            self.on_status("live", f"subscribed {sum(len(t['tokens']) for t in token_list)} instruments")
            sws.subscribe("teji", 2, token_list)   # mode 2 = Quote (includes volume)

        def on_data(wsapp, message):
            try:
                if not self._debugged:
                    print("[angelone] first tick keys:", list(message.keys()))
                    self._debugged = True
                sym = self.token_to_symbol.get(str(message.get("token")))
                ltp_raw = message.get("last_traded_price")
                if sym is None or ltp_raw is None:
                    return
                vol = message.get("volume_trade_for_the_day")
                self.on_tick(sym, float(ltp_raw) / _PAISE, float(vol) if vol is not None else None)
            except Exception as exc:
                print("[angelone] tick parse error:", exc)

        sws.on_open = on_open
        sws.on_data = on_data
        sws.on_error = lambda w, e: self.on_status("error", str(e))
        sws.on_close = lambda w, *a: self.on_status("closed", "websocket closed")
        self._thread = threading.Thread(target=sws.connect, daemon=True)
        self._thread.start()

    def stop(self):
        try:
            if self._sws:
                self._sws.close_connection()
        except Exception:
            pass


class AngelOneExecution(Execution):
    """Places REAL orders. Instantiated only when config mode == 'live'."""
    is_live = True

    def __init__(self, creds, instruments: List[Dict]):
        self.obj, _, _ = _login(creds)
        self.by_symbol = {i["symbol"]: i for i in instruments}

    def market_order(self, symbol: str, side: str, qty: float, ltp: float) -> Fill:
        inst = self.by_symbol[symbol]
        params = {
            "variety": "NORMAL",
            "tradingsymbol": inst["tradingsymbol"],
            "symboltoken": str(inst["token"]),
            "transactiontype": side,
            "exchange": inst["exchange"],
            "ordertype": "MARKET",
            "producttype": "INTRADAY",
            "duration": "DAY",
            "price": "0", "squareoff": "0", "stoploss": "0",
            "quantity": str(int(qty)),
        }
        resp = self.obj.placeOrder(params)
        oid = resp.get("data", {}).get("orderid") if isinstance(resp, dict) else resp
        return Fill(price=ltp, qty=qty, side=side, note=f"LIVE order {oid}")
