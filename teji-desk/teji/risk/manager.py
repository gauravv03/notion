"""Hard risk limits. This layer can only ever make the engine trade LESS.

It gates new entries and forces flat — it never invents trades. Checked before
every entry and on every tick (for stop / target / square-off / kill-switch).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from ..data.candles import now_ist


class RiskManager:
    def __init__(self, cfg: dict, lot_size: int, kill_file: str = "KILL"):
        self.qty_lots = int(cfg.get("qty_lots", 1))
        self.lot_size = int(lot_size)
        self.max_daily_loss = float(cfg.get("max_daily_loss", 3000))
        self.max_trades = int(cfg.get("max_trades", 8))
        self.square_off = str(cfg.get("square_off", "15:20"))
        self.slippage_bps = float(cfg.get("slippage_bps", 2))
        self.kill_file = Path(kill_file)

    @property
    def order_qty(self) -> int:
        return self.qty_lots * self.lot_size

    def kill_switch_engaged(self) -> bool:
        # drop a file named KILL next to the app to force-flat and stop entries
        return self.kill_file.exists()

    def _past_square_off(self, ts: Optional[datetime] = None) -> bool:
        ts = ts or now_ist()
        hh, mm = (int(x) for x in self.square_off.split(":"))
        return (ts.hour, ts.minute) >= (hh, mm)

    def can_enter(self, day_realized: float, closed_trades: int,
                  ts: Optional[datetime] = None) -> Tuple[bool, str]:
        if self.kill_switch_engaged():
            return False, "KILL switch engaged"
        if self._past_square_off(ts):
            return False, f"past square-off ({self.square_off})"
        if day_realized <= -abs(self.max_daily_loss):
            return False, f"daily max loss hit ({self.max_daily_loss})"
        if closed_trades >= self.max_trades:
            return False, f"max trades reached ({self.max_trades})"
        return True, "ok"

    def must_flatten(self, ts: Optional[datetime] = None) -> Tuple[bool, str]:
        if self.kill_switch_engaged():
            return True, "KILL switch engaged"
        if self._past_square_off(ts):
            return True, f"square-off time {self.square_off}"
        return False, ""

    def stop_or_target_hit(self, side: str, ltp: float,
                           stop: Optional[float], target: Optional[float]) -> Optional[str]:
        if side == "LONG":
            if stop is not None and ltp <= stop:
                return "stop-loss hit"
            if target is not None and ltp >= target:
                return "target hit"
        elif side == "SHORT":
            if stop is not None and ltp >= stop:
                return "stop-loss hit"
            if target is not None and ltp <= target:
                return "target hit"
        return None
