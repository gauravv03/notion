"""The engine: live ticks -> candles -> indicators -> strategy -> risk -> fills.

Single-writer: the feed thread drives everything here, and all shared reads go
through the locked State snapshot. Keeps the data path simple and auditable.
"""
from __future__ import annotations

from typing import List, Optional

from .config import Config
from .data.candles import Candle, CandleAggregator, compute_indicators, now_ist
from .strategy.base import Decision, Condition, BUY, SELL, EXIT, HOLD
from .strategy.trend_pulse import TrendPulse
from .risk.manager import RiskManager
from .broker.base import Feed, Execution
from .state import State, Position, Trade


class Engine:
    def __init__(self, cfg: Config, state: State, execution: Execution):
        self.cfg = cfg
        self.state = state
        self.execution = execution
        self.strategy = TrendPulse(cfg.strategy)
        self.risk = RiskManager(cfg.risk, cfg.lot_size)
        self.candles: List[Candle] = []
        self.agg = CandleAggregator(cfg.timeframe_seconds, self._on_candle_close)
        s = cfg.strategy
        self._fast = int(s.get("ema_fast", 9))
        self._slow = int(s.get("ema_slow", 21))
        self._atrp = int(s.get("atr_period", 14))

    # ---- tick path -----------------------------------------------------
    def on_tick(self, price: float, cum_volume: Optional[float]):
        self.state.set_ltp(price)
        self._guard_open_position(price)
        self.agg.on_tick(price, cum_volume)

    def _guard_open_position(self, ltp: float):
        pos = self.state.position
        if pos.side == "FLAT":
            return
        must, why = self.risk.must_flatten()
        if must:
            self._flatten(ltp, why)
            self.state.set_status("halted" if self.risk.kill_switch_engaged() else "live", why)
            return
        hit = self.risk.stop_or_target_hit(pos.side, ltp, pos.stop_loss, pos.target)
        if hit:
            self._flatten(ltp, hit)

    # ---- candle path ---------------------------------------------------
    def _on_candle_close(self, candle: Candle):
        # A bug in strategy/act must never kill the feed thread — log and go on.
        try:
            self.candles.append(candle)
            if len(self.candles) > 500:
                self.candles = self.candles[-500:]
            self.state.push_candle(candle)

            ind = compute_indicators(self.candles, self._fast, self._slow, self._atrp)
            self.state.set_indicators(ind.as_dict())

            decision = self.strategy.evaluate(self.candles, ind, self.state.position.side)
            self.state.set_decision(decision.as_dict())
            self._act(decision, candle.close)
        except Exception as exc:
            import traceback
            print("[engine] candle handler error:", exc)
            traceback.print_exc()
            self.state.set_status(self.state.status, f"handler error: {exc}")

    # ---- acting on a decision -----------------------------------------
    def _act(self, decision: Decision, price: float):
        pos = self.state.position

        if decision.action == EXIT and pos.side != "FLAT":
            self._flatten(price, decision.reason, conditions=[c.as_dict() for c in decision.conditions])
            return

        if decision.action in (BUY, SELL) and pos.side == "FLAT":
            ok, why = self.risk.can_enter(self.state.day_realized,
                                          self.state.trades_closed_count())
            if not ok:
                # surface the block as the current reasoning, don't trade
                blocked = dict(decision.as_dict())
                blocked["action"] = HOLD
                blocked["reason"] = f"Signal fired ({decision.action}) but blocked: {why}."
                self.state.set_decision(blocked)
                return
            self._enter(decision, price)

    def _enter(self, decision: Decision, price: float):
        side = "BUY" if decision.action == BUY else "SELL"
        qty = self.risk.order_qty
        fill = self.execution.market_order(side, qty, price)
        pos = self.state.position
        pos.side = "LONG" if side == "BUY" else "SHORT"
        pos.qty = qty
        pos.avg_price = fill.price
        pos.stop_loss = round(decision.stop_loss, 2) if decision.stop_loss else None
        pos.target = round(decision.target, 2) if decision.target else None
        self.state.record_trade(Trade(
            ts=now_ist().strftime("%H:%M:%S"), action=decision.action, side=pos.side,
            qty=qty, price=fill.price, reason=decision.reason,
            conditions=[c.as_dict() for c in decision.conditions], pnl=None,
        ))

    def _flatten(self, price: float, reason: str, conditions=None):
        pos = self.state.position
        if pos.side == "FLAT":
            return
        close_side = "SELL" if pos.side == "LONG" else "BUY"
        fill = self.execution.market_order(close_side, pos.qty, price)
        if pos.side == "LONG":
            pnl = (fill.price - pos.avg_price) * pos.qty
        else:
            pnl = (pos.avg_price - fill.price) * pos.qty
        closed_side = pos.side
        self.state.record_trade(Trade(
            ts=now_ist().strftime("%H:%M:%S"), action=EXIT, side=closed_side,
            qty=pos.qty, price=fill.price, reason=reason,
            conditions=conditions or [], pnl=pnl,
        ))
        # reset to flat
        self.state.position = Position()
