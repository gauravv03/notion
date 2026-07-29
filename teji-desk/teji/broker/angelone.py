"""Angel One SmartAPI adapter: live WebSocket feed + (gated) live order placement.

Login uses your PIN + a TOTP derived from ANGEL_TOTP_SECRET. The feed streams
quotes over SmartWebSocketV2. Live orders are placed with `placeOrder` and are
ONLY reachable when config `mode: live`.

NOTE: SmartAPI response field names have shifted across SDK versions. The parsing
below is defensive and logged; if your first live connect shows LTP as 0, print
one raw message (see `on_data`) and adjust the key — everything else stays put.
"""
from __future__ import annotations

import threading
from typing import Callable, Optional

import pyotp

from .base import Feed, Execution, Fill

# LTP arrives in paise (integer) — divide to get rupees.
_PAISE = 100.0


def _login(creds):
    """Return (SmartConnect obj, auth_token, feed_token)."""
    from SmartApi import SmartConnect  # provided by smartapi-python

    obj = SmartConnect(api_key=creds.api_key)
    totp = pyotp.TOTP(creds.totp_secret).now()
    session = obj.generateSession(creds.client_code, creds.pin, totp)
    if not session or not session.get("status", False):
        raise RuntimeError(f"Angel One login failed: {session}")
    data = session["data"]
    auth_token = data["jwtToken"]
    feed_token = obj.getfeedToken()
    return obj, auth_token, feed_token


class AngelOneFeed(Feed):
    def __init__(self, on_tick: Callable[[float, Optional[float]], None],
                 creds, exchange_type: int, token: str, on_status=None):
        super().__init__(on_tick)
        self.creds = creds
        self.exchange_type = int(exchange_type)
        self.token = str(token)
        self.on_status = on_status or (lambda s, n="": None)
        self._sws = None
        self._thread: Optional[threading.Thread] = None
        self._debugged = False

    def start(self):
        from SmartApi.smartWebSocketV2 import SmartWebSocketV2

        obj, auth_token, feed_token = _login(self.creds)
        self._obj = obj
        sws = SmartWebSocketV2(auth_token, self.creds.api_key,
                               self.creds.client_code, feed_token)
        self._sws = sws
        corr_id = "teji"
        mode = 2  # Quote mode → includes day volume (needed for VWAP)
        token_list = [{"exchangeType": self.exchange_type, "tokens": [self.token]}]

        def on_open(wsapp):
            self.on_status("live", "websocket open — subscribed")
            sws.subscribe(corr_id, mode, token_list)

        def on_data(wsapp, message):
            try:
                if not self._debugged:
                    # one-time raw dump helps verify field names on a new SDK
                    print("[angelone] first tick keys:", list(message.keys()))
                    self._debugged = True
                ltp_raw = message.get("last_traded_price")
                if ltp_raw is None:
                    return
                ltp = float(ltp_raw) / _PAISE
                vol = message.get("volume_trade_for_the_day")
                vol = float(vol) if vol is not None else None
                self.on_tick(ltp, vol)
            except Exception as exc:  # never let a bad tick kill the socket
                print("[angelone] tick parse error:", exc)

        def on_error(wsapp, error):
            self.on_status("error", str(error))

        def on_close(wsapp, *a):
            self.on_status("closed", "websocket closed")

        sws.on_open = on_open
        sws.on_data = on_data
        sws.on_error = on_error
        sws.on_close = on_close

        # connect() blocks, so run it on its own thread
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

    def __init__(self, creds, instrument: dict):
        self.obj, _, _ = _login(creds)
        self.instrument = instrument

    def market_order(self, side: str, qty: int, ltp: float) -> Fill:
        params = {
            "variety": "NORMAL",
            "tradingsymbol": self.instrument["tradingsymbol"],
            "symboltoken": str(self.instrument["token"]),
            "transactiontype": side,             # BUY | SELL
            "exchange": self.instrument["exchange"],
            "ordertype": "MARKET",
            "producttype": "INTRADAY",
            "duration": "DAY",
            "price": "0",
            "squareoff": "0",
            "stoploss": "0",
            "quantity": str(qty),
        }
        resp = self.obj.placeOrder(params)
        order_id = resp.get("data", {}).get("orderid") if isinstance(resp, dict) else resp
        # We report the LTP as the fill reference; true fill price should be
        # reconciled from the order/trade book in a follow-up (see README TODO).
        return Fill(price=ltp, qty=qty, side=side, note=f"LIVE order {order_id}")
