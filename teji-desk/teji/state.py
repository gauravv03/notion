"""Live, thread-safe state shared between the engine and the dashboard.

Namespaced by instrument symbol. The engine/traders mutate it; the dashboard
reads an immutable snapshot. Secrets are never stored here.
"""
from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional

from .data.candles import Candle, now_ist
from .config import timeframe_label


@dataclass
class Position:
    side: str = "FLAT"
    qty: float = 0.0
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
    action: str
    side: str
    qty: float
    price: float
    reason: str
    conditions: List[dict]
    pnl: Optional[float] = None

    def as_dict(self) -> dict:
        return {
            "ts": self.ts, "action": self.action, "side": self.side,
            "qty": self.qty, "price": round(self.price, 2), "reason": self.reason,
            "conditions": self.conditions,
            "pnl": None if self.pnl is None else round(self.pnl, 2),
        }


@dataclass
class InstrumentState:
    symbol: str
    name: str
    asset_class: str
    feed: str
    enabled: bool = True
    ltp: float = 0.0
    position: Position = field(default_factory=Position)
    candles: Deque[Candle] = field(default_factory=lambda: deque(maxlen=120))
    indicators: dict = field(default_factory=dict)
    last_decision: dict = field(default_factory=dict)
    trades: List[Trade] = field(default_factory=list)


class State:
    def __init__(self, cfg):
        self._lock = threading.RLock()
        self.cfg = cfg
        self.mode = cfg.mode
        self.timeframe = cfg.default_timeframe_seconds
        self.status = "starting"
        self.status_note = ""
        self.halted = False
        self.started_ist = now_ist().strftime("%Y-%m-%d %H:%M:%S")
        self.inst: Dict[str, InstrumentState] = {}
        for i in cfg.instruments:
            self.inst[i["symbol"]] = InstrumentState(
                symbol=i["symbol"], name=i.get("name", i["symbol"]),
                asset_class=i.get("asset_class", "equity"),
                feed=cfg.effective_feed(i),
                enabled=bool(i.get("enabled", True)),
            )
        self.feeds = sorted({s.feed for s in self.inst.values()})

    # ---- mutations -----------------------------------------------------
    def set_status(self, status: str, note: str = ""):
        with self._lock:
            self.status, self.status_note = status, note

    def set_ltp(self, sym: str, ltp: float):
        with self._lock:
            self.inst[sym].ltp = ltp

    def get_ltp(self, sym: str) -> float:
        with self._lock:
            return self.inst[sym].ltp

    def push_candle(self, sym: str, c: Candle):
        with self._lock:
            self.inst[sym].candles.append(c)

    def clear_candles(self, sym: str):
        with self._lock:
            self.inst[sym].candles.clear()
            self.inst[sym].indicators = {}
            self.inst[sym].last_decision = {}

    def set_indicators(self, sym: str, d: dict):
        with self._lock:
            self.inst[sym].indicators = d

    def set_decision(self, sym: str, d: dict):
        with self._lock:
            self.inst[sym].last_decision = d

    def get_position(self, sym: str) -> Position:
        with self._lock:
            return self.inst[sym].position

    def set_position(self, sym: str, pos: Position):
        with self._lock:
            self.inst[sym].position = pos

    def record_trade(self, sym: str, t: Trade):
        with self._lock:
            self.inst[sym].trades.append(t)

    def trades_closed_count(self, sym: str) -> int:
        with self._lock:
            return sum(1 for t in self.inst[sym].trades if t.pnl is not None)

    def is_enabled(self, sym: str) -> bool:
        with self._lock:
            return self.inst[sym].enabled

    def set_enabled(self, sym: str, on: bool):
        with self._lock:
            self.inst[sym].enabled = on

    def set_timeframe(self, seconds: int):
        with self._lock:
            self.timeframe = seconds

    def portfolio_realized(self) -> float:
        with self._lock:
            return sum(t.pnl for s in self.inst.values() for t in s.trades if t.pnl is not None)

    # ---- snapshot ------------------------------------------------------
    def _inst_summary(self, s: InstrumentState) -> dict:
        upnl = s.position.unrealized(s.ltp)
        realized = sum(t.pnl for t in s.trades if t.pnl is not None)
        closed = [t for t in s.trades if t.pnl is not None]
        wins = [t for t in closed if t.pnl > 0]
        return {
            "symbol": s.symbol, "name": s.name, "asset_class": s.asset_class,
            "feed": s.feed, "enabled": s.enabled, "ltp": round(s.ltp, 2),
            "position": {
                "side": s.position.side, "qty": s.position.qty,
                "avg_price": round(s.position.avg_price, 2),
                "stop_loss": s.position.stop_loss, "target": s.position.target,
                "unrealized": round(upnl, 2),
            },
            "day_pnl": round(realized + upnl, 2),
            "trades_count": len(closed),
            "win_rate": round(100 * len(wins) / len(closed)) if closed else 0,
            "indicators": s.indicators,
            "last_decision": s.last_decision,
            "candles": [c.as_dict() for c in s.candles],
            "trades": [t.as_dict() for t in reversed(s.trades[-40:])],
        }

    def snapshot(self) -> dict:
        with self._lock:
            insts = [self._inst_summary(s) for s in self.inst.values()]
            port = sum(i["day_pnl"] for i in insts)
            closed = sum(i["trades_count"] for i in insts)
            return {
                "mode": self.mode,
                "feeds": self.feeds,
                "status": self.status,
                "status_note": self.status_note,
                "halted": self.halted,
                "timeframe": self.timeframe,
                "timeframe_label": timeframe_label(self.timeframe),
                "started_ist": self.started_ist,
                "portfolio_pnl": round(port, 2),
                "portfolio_trades": closed,
                "instruments": insts,
            }
