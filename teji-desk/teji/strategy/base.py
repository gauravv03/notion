"""Strategy interface + the Decision object that carries the *reasoning*.

The whole point of this project: a strategy never just says "BUY". It returns a
Decision whose `conditions` and `reason` explain exactly why — and that is what
the dashboard renders on every trade.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..data.candles import Candle, Indicators

# actions
BUY = "BUY"        # open/increase LONG
SELL = "SELL"      # open/increase SHORT
EXIT = "EXIT"      # flatten current position
HOLD = "HOLD"      # do nothing


@dataclass
class Condition:
    label: str
    passed: bool
    detail: str = ""

    def as_dict(self) -> dict:
        return {"label": self.label, "passed": self.passed, "detail": self.detail}


@dataclass
class Decision:
    action: str                       # BUY | SELL | EXIT | HOLD
    reason: str                       # one-line human summary
    conditions: List[Condition] = field(default_factory=list)
    target_side: Optional[str] = None  # LONG | SHORT | FLAT after this acts
    stop_loss: Optional[float] = None
    target: Optional[float] = None

    def as_dict(self) -> dict:
        return {
            "action": self.action,
            "reason": self.reason,
            "conditions": [c.as_dict() for c in self.conditions],
            "target_side": self.target_side,
            "stop_loss": round(self.stop_loss, 2) if self.stop_loss else None,
            "target": round(self.target, 2) if self.target else None,
        }


class Strategy:
    name = "base"

    def evaluate(self, candles: List[Candle], ind: Indicators, position_side: str) -> Decision:
        """Return a Decision given closed candles, indicators, and current side.

        `position_side` is one of "LONG", "SHORT", "FLAT".
        """
        raise NotImplementedError
