"""Configuration loading: `.env` secrets + `config.yaml` settings.

Secrets live only in the environment (loaded from a git-ignored `.env`); they are
never written to disk by this app and never appear in the dashboard state.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# selectable candle timeframes (label -> seconds)
TIMEFRAMES = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}


def timeframe_label(seconds: int) -> str:
    for k, v in TIMEFRAMES.items():
        if v == seconds:
            return k
    return f"{seconds}s"


def load_env(path: str | os.PathLike = ".env") -> None:
    """Minimal .env loader (no external dependency). Existing env vars win."""
    p = Path(path)
    if not p.exists():
        return
    for raw in p.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


@dataclass
class AngelCreds:
    api_key: str
    client_code: str
    pin: str
    totp_secret: str

    @classmethod
    def from_env(cls) -> "AngelCreds":
        missing = [k for k in
                   ("ANGEL_API_KEY", "ANGEL_CLIENT_CODE", "ANGEL_PIN", "ANGEL_TOTP_SECRET")
                   if not os.environ.get(k)]
        if missing:
            raise RuntimeError(
                "Missing Angel One credentials: " + ", ".join(missing)
                + ".\nCopy .env.example to .env and fill it in (needed only for real "
                  "equity/index data or live orders).")
        return cls(os.environ["ANGEL_API_KEY"], os.environ["ANGEL_CLIENT_CODE"],
                   os.environ["ANGEL_PIN"], os.environ["ANGEL_TOTP_SECRET"])


@dataclass
class Config:
    raw: Dict[str, Any]
    mode: str = "paper"
    default_timeframe_seconds: int = 60
    instruments: List[Dict[str, Any]] = field(default_factory=list)
    crypto: Dict[str, Any] = field(default_factory=dict)
    strategy: Dict[str, Any] = field(default_factory=dict)
    risk: Dict[str, Any] = field(default_factory=dict)
    dashboard: Dict[str, Any] = field(default_factory=dict)
    feed_override: Optional[str] = None   # "mock" forces every instrument to mock

    @classmethod
    def load(cls, path: str | os.PathLike = "config.yaml") -> "Config":
        data = yaml.safe_load(Path(path).read_text()) or {}
        return cls(
            raw=data,
            mode=str(data.get("mode", "paper")).lower(),
            default_timeframe_seconds=int(data.get("default_timeframe_seconds", 60)),
            instruments=data.get("instruments", []),
            crypto=data.get("crypto", {}),
            strategy=data.get("strategy", {}),
            risk=data.get("risk", {}),
            dashboard=data.get("dashboard", {}),
        )

    @property
    def is_live(self) -> bool:
        return self.mode == "live"

    def effective_feed(self, inst: Dict[str, Any]) -> str:
        """Which feed actually serves this instrument, honouring --mock override."""
        if self.feed_override == "mock":
            return "mock"
        return inst.get("feed", "angelone")
