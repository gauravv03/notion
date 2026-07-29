"""Multi-instrument engine + the runtime controller the dashboard drives.

Routes each feed tick to the right Trader, and exposes the in-app controls:
change timeframe, toggle an instrument's trading on/off, trade-all, force-flat.
"""
from __future__ import annotations

from typing import Dict, List

from .config import Config, TIMEFRAMES
from .trader import Trader
from .broker.base import Execution
from .state import State


class Engine:
    def __init__(self, cfg: Config, state: State, execution: Execution):
        self.cfg = cfg
        self.state = state
        self.execution = execution
        self.timeframe = cfg.default_timeframe_seconds
        self.traders: Dict[str, Trader] = {}
        for inst in cfg.instruments:
            self.traders[inst["symbol"]] = Trader(
                cfg, inst, state, execution,
                portfolio_realized=self.state.portfolio_realized,
                timeframe=self.timeframe,
            )

    # ---- feed routing --------------------------------------------------
    def on_tick(self, symbol: str, price: float, cum_volume):
        t = self.traders.get(symbol)
        if t is not None:
            t.on_tick(price, cum_volume)

    # ---- controller API (called from the dashboard) --------------------
    def set_timeframe(self, seconds: int) -> dict:
        if seconds not in TIMEFRAMES.values():
            return {"ok": False, "error": f"unsupported timeframe {seconds}"}
        self.timeframe = seconds
        for t in self.traders.values():
            t.set_timeframe(seconds)
        self.state.set_timeframe(seconds)
        return {"ok": True, "timeframe": seconds}

    def toggle(self, symbol: str, enabled: bool) -> dict:
        if symbol not in self.traders:
            return {"ok": False, "error": "unknown symbol"}
        self.state.set_enabled(symbol, enabled)
        return {"ok": True, "symbol": symbol, "enabled": enabled}

    def trade_all(self, enabled: bool) -> dict:
        for sym in self.traders:
            self.state.set_enabled(sym, enabled)
        return {"ok": True, "enabled": enabled}

    def engage_kill(self) -> dict:
        from pathlib import Path
        Path("KILL").write_text("engaged")
        self.state.halted = True
        return {"ok": True}

    def flatten_all(self, reason: str = "shutdown"):
        for t in self.traders.values():
            try:
                t._flatten(self.state.get_ltp(t.symbol), reason)
            except Exception:
                pass
