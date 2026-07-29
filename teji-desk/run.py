#!/usr/bin/env python3
"""TEJI Desk entrypoint.

    python run.py                 # use config.yaml as-is (default: paper + mock feed)
    python run.py --mock          # force the offline synthetic feed
    python run.py --live-data     # force real Angel One feed (still paper fills unless mode: live)
    python run.py --port 8899

Live ORDER placement (real money) additionally requires config `mode: live` AND
the environment variable ALLOW_LIVE=1 — a deliberate two-key safety.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

from teji.config import Config, AngelCreds, load_env
from teji.state import State
from teji.engine import Engine
from teji.broker.paper import PaperExecution
from teji.dashboard.server import serve_in_background


def build_execution(cfg, creds_getter):
    if cfg.is_live:
        if os.environ.get("ALLOW_LIVE") != "1":
            sys.exit("REFUSING to run live: set ALLOW_LIVE=1 to confirm real-money orders.")
        from teji.broker.angelone import AngelOneExecution
        print("\n  ⚠  LIVE MODE — real orders will be placed with real money.\n")
        return AngelOneExecution(creds_getter(), cfg.instrument)
    return PaperExecution(slippage_bps=float(cfg.risk.get("slippage_bps", 2)))


def build_feed(cfg, engine, state, creds_getter):
    if cfg.feed == "angelone":
        from teji.broker.angelone import AngelOneFeed
        return AngelOneFeed(
            engine.on_tick, creds_getter(),
            exchange_type=cfg.instrument.get("exchange_type", 2),
            token=cfg.instrument.get("token"),
            on_status=state.set_status,
        )
    from teji.broker.mock_feed import MockFeed
    return MockFeed(engine.on_tick, start_price=24500.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--mock", action="store_true", help="force synthetic feed")
    ap.add_argument("--live-data", action="store_true", help="force real Angel One feed")
    ap.add_argument("--port", type=int, default=None)
    args = ap.parse_args()

    load_env()
    cfg = Config.load(args.config)
    if args.mock:
        cfg.feed = "mock"
    if args.live_data:
        cfg.feed = "angelone"
    if args.port:
        cfg.dashboard["port"] = args.port

    _creds_cache = {}
    def creds_getter():
        if "c" not in _creds_cache:
            _creds_cache["c"] = AngelCreds.from_env()
        return _creds_cache["c"]

    state = State(cfg)
    execution = build_execution(cfg, creds_getter)
    engine = Engine(cfg, state, execution)
    feed = build_feed(cfg, engine, state, creds_getter)

    host = cfg.dashboard.get("host", "127.0.0.1")
    port = int(cfg.dashboard.get("port", 8899))
    serve_in_background(state, host, port)

    banner(cfg, host, port)
    state.set_status("live", f"{cfg.feed} feed")
    feed.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down — flattening any open position...")
        try:
            engine._flatten(state.ltp, "shutdown")
        except Exception:
            pass
        feed.stop()


def banner(cfg, host, port):
    line = "─" * 58
    print(f"""
┌{line}┐
   TEJI DESK   ·   तेजी
   mode : {cfg.mode.upper():<8}   feed : {cfg.feed.upper()}
   fills: {'REAL ORDERS' if cfg.is_live else 'PAPER (simulated on live prices)'}
   inst : {cfg.instrument.get('name')}  ({cfg.instrument.get('tradingsymbol')})
   strat: {cfg.strategy.get('name')}  EMA{cfg.strategy.get('ema_fast')}/{cfg.strategy.get('ema_slow')} + VWAP

   dashboard →  http://{host}:{port}
   kill switch → create a file named  KILL  (or hit Force-Flat in the UI)
└{line}┘
""")


if __name__ == "__main__":
    main()
