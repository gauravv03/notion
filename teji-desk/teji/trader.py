"""A Trader = one instrument's full loop: candles -> indicators -> strategy ->
risk -> fills. The Engine owns one Trader per instrument in the watchlist.

Kept deliberately close to the original single-instrument path (which was tested
end-to-end); the only change is that state is namespaced by symbol and the
portfolio-level daily-loss check reads aggregate realized P&L.
"""
from __future__ import annotations

import traceback
from typing import Callable, Dict, List

from .config import Config
from .data.candles import Candle, CandleAggregator, compute_indicators, now_ist
from .strategy.trend_pulse import TrendPulse
from .strategy.base import BUY, SELL, EXIT, HOLD
from .risk.manager import RiskManager
from .broker.base import Execution
from .state import State, Position, Trade


class Trader:
    def __init__(self, cfg: Config, inst: Dict, state: State, execution: Execution,
                 portfolio_realized: Callable[[], float], timeframe: int):
        self.cfg = cfg
        self.inst = inst
        self.symbol = inst["symbol"]
        self.state = state
        self.execution = execution
        self.portfolio_realized = portfolio_realized
        self.strategy = TrendPulse(cfg.strategy)
        self.risk = RiskManager(cfg.risk, float(inst.get("lot_size", 1)))
        self.candles: List[Candle] = []
        s = cfg.strategy
        self._fast = int(s.get("ema_fast", 9))
        self._slow = int(s.get("ema_slow", 21))
        self._atrp = int(s.get("atr_period", 14))
        self.timeframe = timeframe
        self.agg = CandleAggregator(timeframe, self._on_candle_close)

    # ---- runtime reconfig ---------------------------------------------
    def set_timeframe(self, seconds: int):
        self.timeframe = seconds
        self.candles = []
        self.strategy = TrendPulse(self.cfg.strategy)   # reset warm-up/cooldown state
        self.agg = CandleAggregator(seconds, self._on_candle_close)
        self.state.clear_candles(self.symbol)

    # ---- tick path -----------------------------------------------------
    def on_tick(self, price: float, cum_volume):
        self.state.set_ltp(self.symbol, price)
        self._guard_open_position(price)
        self.agg.on_tick(price, cum_volume)

    def _guard_open_position(self, ltp: float):
        pos = self.state.get_position(self.symbol)
        if pos.side == "FLAT":
            return
        must, why = self.risk.must_flatten()
        if must:
            self._flatten(ltp, why)
            return
        hit = self.risk.stop_or_target_hit(pos.side, ltp, pos.stop_loss, pos.target)
        if hit:
            self._flatten(ltp, hit)

    # ---- candle path ---------------------------------------------------
    def _on_candle_close(self, candle: Candle):
        try:
            self.candles.append(candle)
            if len(self.candles) > 500:
                self.candles = self.candles[-500:]
            self.state.push_candle(self.symbol, candle)

            ind = compute_indicators(self.candles, self._fast, self._slow, self._atrp)
            self.state.set_indicators(self.symbol, ind.as_dict())

            pos_side = self.state.get_position(self.symbol).side
            decision = self.strategy.evaluate(self.candles, ind, pos_side)
            self.state.set_decision(self.symbol, decision.as_dict())
            self._act(decision, candle.close)
        except Exception as exc:
            print(f"[{self.symbol}] candle handler error:", exc)
            traceback.print_exc()

    def _act(self, decision, price: float):
        pos = self.state.get_position(self.symbol)

        if decision.action == EXIT and pos.side != "FLAT":
            self._flatten(price, decision.reason,
                          conditions=[c.as_dict() for c in decision.conditions])
            return

        if decision.action in (BUY, SELL) and pos.side == "FLAT":
            if not self.state.is_enabled(self.symbol):
                self._show_blocked(decision, "trading disabled for this instrument")
                return
            ok, why = self.risk.can_enter(self.portfolio_realized(),
                                          self.state.trades_closed_count(self.symbol))
            if not ok:
                self._show_blocked(decision, why)
                return
            self._enter(decision, price)

    def _show_blocked(self, decision, why: str):
        d = dict(decision.as_dict())
        d["action"] = HOLD
        d["reason"] = f"Signal fired ({decision.action}) but blocked: {why}."
        self.state.set_decision(self.symbol, d)

    def _enter(self, decision, price: float):
        side = "BUY" if decision.action == BUY else "SELL"
        qty = self.risk.order_qty
        fill = self.execution.market_order(self.symbol, side, qty, price)
        pos = Position(
            side="LONG" if side == "BUY" else "SHORT",
            qty=qty, avg_price=fill.price,
            stop_loss=round(decision.stop_loss, 2) if decision.stop_loss else None,
            target=round(decision.target, 2) if decision.target else None,
        )
        self.state.set_position(self.symbol, pos)
        self.state.record_trade(self.symbol, Trade(
            ts=now_ist().strftime("%H:%M:%S"), action=decision.action, side=pos.side,
            qty=qty, price=fill.price, reason=decision.reason,
            conditions=[c.as_dict() for c in decision.conditions], pnl=None,
        ))

    def _flatten(self, price: float, reason: str, conditions=None):
        pos = self.state.get_position(self.symbol)
        if pos.side == "FLAT":
            return
        close_side = "SELL" if pos.side == "LONG" else "BUY"
        fill = self.execution.market_order(self.symbol, close_side, pos.qty, price)
        if pos.side == "LONG":
            pnl = (fill.price - pos.avg_price) * pos.qty
        else:
            pnl = (pos.avg_price - fill.price) * pos.qty
        self.state.record_trade(self.symbol, Trade(
            ts=now_ist().strftime("%H:%M:%S"), action=EXIT, side=pos.side,
            qty=pos.qty, price=fill.price, reason=reason,
            conditions=conditions or [], pnl=pnl,
        ))
        self.state.set_position(self.symbol, Position())
