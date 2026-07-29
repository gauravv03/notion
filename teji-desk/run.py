#!/usr/bin/env python3
"""TEJI Desk entrypoint (multi-instrument).

    python run.py                 # config.yaml as-is (default: paper, per-instrument feeds)
    python run.py --mock          # force every instrument onto the offline synthetic feed
    python run.py --live-data     # force real feeds (angelone + crypto), still paper fills
    python run.py --port 8899

Live ORDER placement (real money) additionally requires config `mode: live` AND
the environment variable ALLOW_LIVE=1 — a deliberate two-key safety. (Live equity
orders go via Angel One; live crypto orders need a separate exchange adapter — see
README — so crypto stays paper for now even in live mode.)
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from collections import defaultdict

from teji.config import Config, AngelCreds, load_env, timeframe_label
from teji.state import State
from teji.engine import Engine
from teji.broker.paper import PaperExecution
from teji.dashboard.server import serve_in_background


def build_execution(cfg, creds_getter):
    if cfg.is_live:
        if os.environ.get("ALLOW_LIVE") != "1":
            sys.exit("REFUSING to run live: set ALLOW_LIVE=1 to confirm real-money orders.")
        from teji.broker.angelone import AngelOneExecution
        print("\n  ⚠  LIVE MODE — real Angel One orders will be placed with real money.\n")
        equities = [i for i in cfg.instruments if cfg.effective_feed(i) == "angelone"]
        return AngelOneExecution(creds_getter(), equities)
    return PaperExecution(slippage_bps=float(cfg.risk.get("slippage_bps", 2)))


def build_feeds(cfg, engine, state, creds_getter):
    """One feed per distinct source, each serving its subset of instruments."""
    groups = defaultdict(list)
    for inst in cfg.instruments:
        groups[cfg.effective_feed(inst)].append(inst)

    feeds = []
    for source, insts in groups.items():
        if source == "mock":
            from teji.broker.mock_feed import MockFeed
            feeds.append(MockFeed(engine.on_tick, insts))
        elif source == "crypto":
            from teji.broker.crypto_feed import CryptoFeed
            feeds.append(CryptoFeed(engine.on_tick, insts,
                                    poll_seconds=cfg.crypto.get("poll_seconds", 3),
                                    on_status=state.set_status))
        elif source == "angelone":
            from teji.broker.angelone import AngelOneFeed
            feeds.append(AngelOneFeed(engine.on_tick, creds_getter(), insts,
                                      on_status=state.set_status))
        else:
            print(f"[run] unknown feed source '{source}' — skipping {[i['symbol'] for i in insts]}")
    return feeds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--mock", action="store_true", help="force synthetic feed for all")
    ap.add_argument("--live-data", action="store_true", help="force real feeds")
    ap.add_argument("--port", type=int, default=None)
    args = ap.parse_args()

    load_env()
    cfg = Config.load(args.config)
    if args.mock:
        cfg.feed_override = "mock"
    if args.live_data:
        cfg.feed_override = None
    if args.port:
        cfg.dashboard["port"] = args.port

    _cache = {}
    def creds_getter():
        if "c" not in _cache:
            _cache["c"] = AngelCreds.from_env()
        return _cache["c"]

    state = State(cfg)
    execution = build_execution(cfg, creds_getter)
    engine = Engine(cfg, state, execution)
    feeds = build_feeds(cfg, engine, state, creds_getter)

    host = cfg.dashboard.get("host", "127.0.0.1")
    port = int(cfg.dashboard.get("port", 8899))
    serve_in_background(state, engine, host, port)

    banner(cfg, state, host, port)
    state.set_status("live", "feeds starting")
    for f in feeds:
        f.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down — flattening all open positions...")
        engine.flatten_all("shutdown")
        for f in feeds:
            f.stop()


def banner(cfg, state, host, port):
    line = "─" * 58
    names = ", ".join(i.get("symbol") for i in cfg.instruments)
    print(f"""
┌{line}┐
   TEJI DESK   ·   तेजी   ·   multi-instrument
   mode : {cfg.mode.upper():<6}  fills: {'REAL ORDERS' if cfg.is_live else 'PAPER (simulated on live prices)'}
   feeds: {', '.join(state.feeds)}
   timeframe : {timeframe_label(cfg.default_timeframe_seconds)}  (switch live in the UI)
   watchlist : {names}
   strategy  : {cfg.strategy.get('name')}  EMA{cfg.strategy.get('ema_fast')}/{cfg.strategy.get('ema_slow')} + VWAP

   dashboard →  http://{host}:{port}
   kill switch → create a file named  KILL  (or hit Force-Flat in the UI)
└{line}┘
""")


if __name__ == "__main__":
    main()
