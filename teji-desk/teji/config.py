"""Configuration loading: `.env` secrets + `config.yaml` settings.

Secrets live only in the environment (loaded from a git-ignored `.env`); they are
never written to disk by this app and never appear in the dashboard state.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

import yaml


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
        key, val = key.strip(), val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


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
                "Missing Angel One credentials in environment: "
                + ", ".join(missing)
                + ".\nCopy .env.example to .env and fill it in (needed only for feed=angelone or mode=live)."
            )
        return cls(
            api_key=os.environ["ANGEL_API_KEY"],
            client_code=os.environ["ANGEL_CLIENT_CODE"],
            pin=os.environ["ANGEL_PIN"],
            totp_secret=os.environ["ANGEL_TOTP_SECRET"],
        )


@dataclass
class Config:
    raw: Dict[str, Any]

    mode: str = "paper"
    feed: str = "mock"
    instrument: Dict[str, Any] = field(default_factory=dict)
    timeframe_seconds: int = 60
    strategy: Dict[str, Any] = field(default_factory=dict)
    risk: Dict[str, Any] = field(default_factory=dict)
    dashboard: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | os.PathLike = "config.yaml") -> "Config":
        data = yaml.safe_load(Path(path).read_text()) or {}
        return cls(
            raw=data,
            mode=str(data.get("mode", "paper")).lower(),
            feed=str(data.get("feed", "mock")).lower(),
            instrument=data.get("instrument", {}),
            timeframe_seconds=int(data.get("timeframe_seconds", 60)),
            strategy=data.get("strategy", {}),
            risk=data.get("risk", {}),
            dashboard=data.get("dashboard", {}),
        )

    # convenience accessors ------------------------------------------------
    @property
    def is_live(self) -> bool:
        return self.mode == "live"

    @property
    def lot_size(self) -> int:
        return int(self.instrument.get("lot_size", 1))
