"""Live, thread-safe state shared between the engine and the dashboard.

The engine mutates it; the dashboard reads an immutable snapshot. Secrets are
never stored here.
"""
from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional

from .data.candles import Candle, now_ist


@dataclass
class Position:
    side: str = "FLAT"          # LONG | SHORT | FLAT
    qty: int = 0                # absolute quantity (units, not lots)
    avg_price: float = 0.0
    stop_loss: Optional[float] = None
    target: Optional[float] = None

    def unrealized(self, ltp: float) -> float:
        if self.side == "LONG":
            return (ltp - self.avg_price) * self.qty
        if self.side == "SHORT":
            return (self.avg_price - ltp) * self.qty
        return 0.0


@dataclass
class Trade:
    ts: str
    action: str          # BUY | SELL | EXIT
    side: str            # resulting or closed side
    qty: int
    price: float
    reason: str
    conditions: List[dict]
    pnl: Optional[float] = None   # realized pnl if this closed a position

    def as_dict(self) -> dict:
        return {
            "ts": self.ts, "action": self.action, "side": self.side,
            "qty": self.qty, "price": round(self.price, 2), "reason": self.reason,
            "conditions": self.conditions,
            "pnl": None if self.pnl is None else round(self.pnl, 2),
        }


class State:
    def __init__(self, cfg):
        self._lock = threading.RLock()
        self.cfg = cfg
        self.mode = cfg.mode
        self.feed = cfg.feed
        self.instrument = cfg.instrument
        self.status = "starting"          # starting | live | halted | closed
        self.status_note = ""
        self.ltp: float = 0.0
        self.position = Position()
        self.candles: Deque[Candle] = deque(maxlen=120)
        self.indicators: dict = {}
        self.last_decision: dict = {}     # most recent Decision (even HOLD)
        self.trades: List[Trade] = []
        self.day_realized: float = 0.0
        self.day_high_equity: float = 0.0
        self.halted: bool = False
        self.started_ist: str = now_ist().strftime("%Y-%m-%d %H:%M:%S")

    # ---- mutations (call from engine thread) ---------------------------
    def set_status(self, status: str, note: str = ""):
        with self._lock:
            self.status, self.status_note = status, note

    def set_ltp(self, ltp: float):
        with self._lock:
            self.ltp = ltp

    def push_candle(self, c: Candle):
        with self._lock:
            self.candles.append(c)

    def set_indicators(self, d: dict):
        with self._lock:
            self.indicators = d

    def set_decision(self, d: dict):
        with self._lock:
            self.last_decision = d

    def record_trade(self, t: Trade):
        with self._lock:
            self.trades.append(t)
            if t.pnl is not None:
                self.day_realized += t.pnl

    def trades_closed_count(self) -> int:
        with self._lock:
            return sum(1 for t in self.trades if t.pnl is not None)

    # ---- snapshot (call from dashboard thread) -------------------------
    def snapshot(self) -> dict:
        with self._lock:
            upnl = self.position.unrealized(self.ltp)
            equity = self.day_realized + upnl
            wins = [t for t in self.trades if t.pnl is not None and t.pnl > 0]
            closed = [t for t in self.trades if t.pnl is not None]
            return {
                "mode": self.mode,
                "feed": self.feed,
                "status": self.status,
                "status_note": self.status_note,
                "halted": self.halted,
                "started_ist": self.started_ist,
                "instrument": {
                    "name": self.instrument.get("name"),
                    "tradingsymbol": self.instrument.get("tradingsymbol"),
                    "lot_size": self.instrument.get("lot_size"),
                },
                "ltp": round(self.ltp, 2),
                "position": {
                    "side": self.position.side,
                    "qty": self.position.qty,
                    "avg_price": round(self.position.avg_price, 2),
                    "stop_loss": self.position.stop_loss,
                    "target": self.position.target,
                    "unrealized": round(upnl, 2),
                },
                "day_pnl": round(equity, 2),
                "day_realized": round(self.day_realized, 2),
                "trades_count": len(closed),
                "win_rate": round(100 * len(wins) / len(closed)) if closed else 0,
                "indicators": self.indicators,
                "last_decision": self.last_decision,
                "candles": [c.as_dict() for c in self.candles],
                "trades": [t.as_dict() for t in reversed(self.trades[-40:])],
            }
