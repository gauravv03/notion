"""Tick aggregation into candles + the indicators TrendPulse needs.

Everything here is pure Python (no pandas/numpy) so the whole thing installs in
seconds and is easy to read line by line — which matters when real money is the
eventual destination.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Callable, List, Optional

IST = timezone(timedelta(hours=5, minutes=30))


def now_ist() -> datetime:
    return datetime.now(IST)


@dataclass
class Candle:
    start: datetime          # candle open time (IST)
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    def as_dict(self) -> dict:
        return {
            "t": self.start.strftime("%H:%M:%S"),
            "o": round(self.open, 2), "h": round(self.high, 2),
            "l": round(self.low, 2), "c": round(self.close, 2),
            "v": round(self.volume, 2),
        }


class CandleAggregator:
    """Feeds ticks in, emits closed candles via `on_close`."""

    def __init__(self, timeframe_seconds: int, on_close: Callable[[Candle], None]):
        self.tf = timeframe_seconds
        self.on_close = on_close
        self.current: Optional[Candle] = None
        self._last_cum_volume: Optional[float] = None  # brokers send cumulative day volume

    def _bucket_start(self, ts: datetime) -> datetime:
        epoch = int(ts.timestamp())
        floored = epoch - (epoch % self.tf)
        return datetime.fromtimestamp(floored, IST)

    def on_tick(self, price: float, cum_volume: Optional[float], ts: Optional[datetime] = None) -> None:
        ts = ts or now_ist()
        bstart = self._bucket_start(ts)

        # convert cumulative day-volume into per-tick delta (0 if unavailable)
        vol_delta = 0.0
        if cum_volume is not None:
            if self._last_cum_volume is not None and cum_volume >= self._last_cum_volume:
                vol_delta = cum_volume - self._last_cum_volume
            self._last_cum_volume = cum_volume

        if self.current is None:
            self.current = Candle(bstart, price, price, price, price, vol_delta)
            return

        if bstart > self.current.start:
            # close the running candle and start a new one
            closed = self.current
            self.current = Candle(bstart, price, price, price, price, vol_delta)
            self.on_close(closed)
        else:
            c = self.current
            c.high = max(c.high, price)
            c.low = min(c.low, price)
            c.close = price
            c.volume += vol_delta


# ---- indicators ---------------------------------------------------------

def ema(values: List[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    e = sum(values[:period]) / period  # seed with SMA
    for v in values[period:]:
        e = v * k + e * (1 - k)
    return e


def atr(candles: List[Candle], period: int) -> Optional[float]:
    if len(candles) < period + 1:
        return None
    trs: List[float] = []
    for i in range(1, len(candles)):
        h, l, pc = candles[i].high, candles[i].low, candles[i - 1].close
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    # Wilder's smoothing
    a = sum(trs[:period]) / period
    for tr in trs[period:]:
        a = (a * (period - 1) + tr) / period
    return a


@dataclass
class Indicators:
    ema_fast: Optional[float] = None
    ema_slow: Optional[float] = None
    ema_fast_prev: Optional[float] = None
    ema_slow_prev: Optional[float] = None
    vwap: Optional[float] = None
    atr: Optional[float] = None
    close: Optional[float] = None
    vwap_has_volume: bool = False

    def as_dict(self) -> dict:
        def r(x): return round(x, 2) if isinstance(x, (int, float)) else None
        return {
            "ema_fast": r(self.ema_fast), "ema_slow": r(self.ema_slow),
            "vwap": r(self.vwap), "atr": r(self.atr), "close": r(self.close),
            "vwap_has_volume": self.vwap_has_volume,
        }


def compute_indicators(candles: List[Candle], fast: int, slow: int, atr_period: int) -> Indicators:
    closes = [c.close for c in candles]
    ind = Indicators(close=closes[-1] if closes else None)
    ind.ema_fast = ema(closes, fast)
    ind.ema_slow = ema(closes, slow)
    ind.ema_fast_prev = ema(closes[:-1], fast) if len(closes) > 1 else None
    ind.ema_slow_prev = ema(closes[:-1], slow) if len(closes) > 1 else None
    ind.atr = atr(candles, atr_period)

    # session VWAP: use volume if the instrument provides it, else equal-weight
    # the typical price (a documented fallback for volume-less spot indices).
    total_vol = sum(c.volume for c in candles)
    if total_vol > 0:
        pv = sum(((c.high + c.low + c.close) / 3) * c.volume for c in candles)
        ind.vwap = pv / total_vol
        ind.vwap_has_volume = True
    elif candles:
        tp = [((c.high + c.low + c.close) / 3) for c in candles]
        ind.vwap = sum(tp) / len(tp)
        ind.vwap_has_volume = False
    return ind
