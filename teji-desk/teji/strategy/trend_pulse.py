"""TrendPulse — a transparent EMA-trend + VWAP-confirmation strategy.

Rules (intraday, one position at a time):

  Go LONG  when EMA_fast is above EMA_slow  AND  price is above VWAP
  Go SHORT when EMA_fast is below EMA_slow  AND  price is below VWAP
  EXIT     when the fast/slow relationship flips against the open position
           (stop-loss / target / square-off are enforced by the risk layer)

Entries fire on *alignment* (both conditions agree), not only on the single
crossover tick — that keeps the desk actually taking the trend while still
demanding VWAP confirmation. After any exit there's a short re-entry cooldown so
one flip doesn't immediately re-arm the same trade.

Stop-loss and target come from ATR so they're visible on the ticket:
  stop   = entry -/+ atr_stop_mult * ATR
  target = entry +/- reward_risk * (entry - stop)

Nothing here is hidden — swap it for your own edge via the same evaluate() contract.
"""
from __future__ import annotations

from typing import List

from ..data.candles import Candle, Indicators
from .base import Strategy, Decision, Condition, BUY, SELL, EXIT, HOLD


class TrendPulse(Strategy):
    name = "trend_pulse"

    def __init__(self, cfg: dict):
        self.fast = int(cfg.get("ema_fast", 9))
        self.slow = int(cfg.get("ema_slow", 21))
        self.use_vwap = bool(cfg.get("use_vwap", True))
        self.atr_stop_mult = float(cfg.get("atr_stop_mult", 1.5))
        self.reward_risk = float(cfg.get("reward_risk", 2.0))
        self.cooldown = int(cfg.get("reentry_cooldown_bars", 3))
        # internal state (this strategy instance is long-lived)
        self._bars = 0
        self._cooldown_until = 0
        self._prev_side = "FLAT"

    def _levels(self, entry: float, atr: float, long: bool):
        if not atr or atr <= 0:
            return None, None
        risk = self.atr_stop_mult * atr
        if long:
            return entry - risk, entry + self.reward_risk * risk
        return entry + risk, entry - self.reward_risk * risk

    def evaluate(self, candles: List[Candle], ind: Indicators, position_side: str) -> Decision:
        self._bars += 1
        # detect that a position was just closed -> start a re-entry cooldown
        if self._prev_side != "FLAT" and position_side == "FLAT":
            self._cooldown_until = self._bars + self.cooldown
        self._prev_side = position_side

        if (ind.ema_fast is None or ind.ema_slow is None
                or ind.ema_fast_prev is None or ind.ema_slow_prev is None):
            return Decision(HOLD, "Warming up — not enough candles for EMAs yet.",
                            [Condition(f"EMA{self.fast}/EMA{self.slow} ready", False,
                                       f"need > {self.slow} candles")])

        f, s = ind.ema_fast, ind.ema_slow
        fp, sp = ind.ema_fast_prev, ind.ema_slow_prev
        close, vwap = ind.close, ind.vwap

        crossed_up = fp <= sp and f > s
        crossed_down = fp >= sp and f < s
        fast_above = f > s
        above_vwap = (vwap is None) or (close > vwap)
        below_vwap = (vwap is None) or (close < vwap)
        vwap_note = "" if ind.vwap_has_volume else " (session-mean fallback)"

        def c_ema(up: bool):
            return Condition(
                f"EMA{self.fast} {'above' if up else 'below'} EMA{self.slow}",
                fast_above if up else (not fast_above),
                f"EMA{self.fast}={f:.1f}  EMA{self.slow}={s:.1f}",
            )

        def c_vwap(long: bool):
            if not self.use_vwap:
                return Condition("VWAP filter", True, "disabled")
            ok = above_vwap if long else below_vwap
            return Condition(
                f"Price {'above' if long else 'below'} VWAP", ok,
                (f"close={close:.1f}  vwap={vwap:.1f}{vwap_note}" if vwap else "vwap n/a"),
            )

        # ---- exits: flip against an open position -----------------------
        if position_side == "LONG" and crossed_down:
            return Decision(EXIT, "Trend flipped down — EMA fast crossed below slow. Close LONG.",
                            [c_ema(False)], target_side="FLAT")
        if position_side == "SHORT" and crossed_up:
            return Decision(EXIT, "Trend flipped up — EMA fast crossed above slow. Close SHORT.",
                            [c_ema(True)], target_side="FLAT")

        # ---- entries on alignment (only when flat, past cooldown) -------
        if position_side == "FLAT":
            in_cooldown = self._bars < self._cooldown_until
            long_ok = fast_above and (above_vwap or not self.use_vwap)
            short_ok = (not fast_above) and (below_vwap or not self.use_vwap)

            if in_cooldown and (long_ok or short_ok):
                return Decision(HOLD, f"Signal aligned but in re-entry cooldown ({self._cooldown_until - self._bars} bars left).",
                                [c_ema(long_ok), c_vwap(long_ok)])

            if long_ok:
                stop, target = self._levels(close, ind.atr, True)
                why = ("BUY — EMA{f} just crossed above EMA{s} with price above VWAP. Go LONG."
                       if crossed_up else
                       "BUY — trend aligned: EMA{f} above EMA{s} and price above VWAP. Go LONG.")
                return Decision(BUY, why.format(f=self.fast, s=self.slow),
                                [c_ema(True), c_vwap(True)],
                                target_side="LONG", stop_loss=stop, target=target)
            if short_ok:
                stop, target = self._levels(close, ind.atr, False)
                why = ("SELL — EMA{f} just crossed below EMA{s} with price below VWAP. Go SHORT."
                       if crossed_down else
                       "SELL — trend aligned: EMA{f} below EMA{s} and price below VWAP. Go SHORT.")
                return Decision(SELL, why.format(f=self.fast, s=self.slow),
                                [c_ema(False), c_vwap(False)],
                                target_side="SHORT", stop_loss=stop, target=target)

        # ---- otherwise hold, but show exactly what we're watching -------
        watching = [c_ema(True), c_vwap(True)]
        reason = ("Holding — EMA/VWAP not aligned for an entry."
                  if position_side == "FLAT"
                  else f"Holding {position_side} — trend intact, no exit signal.")
        return Decision(HOLD, reason, watching)
