# TEJI Desk — a transparent, live-data intraday trading engine (Indian markets)

TEJI Desk connects to **Angel One SmartAPI**, streams **live** market data, runs a
**transparent** rule-based strategy, and shows you — on a live dashboard — the
running position and the *exact logic* behind every buy and sell.

It is **paper-first by design**: real prices in, real signals, real reasoning,
but **simulated fills** until you deliberately switch to live orders. Nothing here
invents prices except the offline `mock` feed, which is labelled as such everywhere.

> **This is engineering scaffolding, not investment advice, and not a money
> machine.** A strategy that executes cleanly is *not* the same as a strategy that
> is profitable. The default strategy (TrendPulse) is a well-known, deliberately
> simple example so you can see the machinery working — the edge is yours to build.

---

## What you get

```
Angel One WebSocket (live ticks)
        │
        ▼
  Candle aggregator ──► Indicators (EMA fast/slow, VWAP, ATR)
        │
        ▼
  Strategy (TrendPulse) ──► Decision { action, reason, conditions… }   ← the "why"
        │
        ▼
  Risk manager (size, daily max-loss, square-off, kill-switch)
        │
        ▼
  Execution:  Paper (simulated on live price)   |   Angel One (REAL orders, gated)
        │
        ▼
  Live dashboard  (position running · live decision · execution log)
```

Every trade the engine takes is recorded **with the conditions that produced it**
(e.g. `EMA9 above EMA21 ✓`, `Price above VWAP ✓`) and every exit records *why*
(`target hit`, `stop-loss hit`, `square-off`, `trend flipped`).

---

## Run it right now (no account needed)

Requires Python 3.10+.

```bash
cd teji-desk
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # PyYAML alone is enough for the mock feed
python run.py --mock
```

Open **http://127.0.0.1:8899**. You'll see the full pipeline running on a synthetic
feed: candles form, TrendPulse takes paper positions, and the execution log fills
in with reasoning. This is the exact UI you'll use with live data — only the price
source changes.

---

## Connect live Angel One data (still paper fills — recommended next step)

1. Create a SmartAPI app at **https://smartapi.angelbroking.com/** and note the API key.
2. Enable **TOTP** on your Angel One account and keep the **base32 secret**.
3. Copy credentials into a local, git-ignored `.env`:
   ```bash
   cp .env.example .env
   # then fill ANGEL_API_KEY / ANGEL_CLIENT_CODE / ANGEL_PIN / ANGEL_TOTP_SECRET
   ```
4. Pick the instrument to trade and get its token:
   ```bash
   python tools/find_token.py "BANKNIFTY"      # prints token + exch_seg + lot size
   ```
   Put `token`, `tradingsymbol`, `exchange`, `exchange_type` and `lot_size` into
   `config.yaml`. Prefer a **future / option / stock** (they carry volume, so VWAP is
   real); the spot index has no volume and VWAP falls back to a session-mean.
5. Run with the real feed, fills still simulated:
   ```bash
   python run.py --live-data          # feed: angelone, mode stays: paper
   ```

Now you're watching the strategy react to the real tape, with zero money at risk.
Let it run across a few sessions and judge it honestly before going further.

---

## Going live (real orders, real money)

Only when you trust it. Two keys are required, on purpose:

1. In `config.yaml` set `mode: live`.
2. In the environment set `ALLOW_LIVE=1`.

```bash
ALLOW_LIVE=1 python run.py --live-data
```

Hard risk limits always apply (see `config.yaml → risk`):

- `qty_lots` — position size in lots.
- `max_daily_loss` — engine stops opening new trades once hit.
- `max_trades` — per-day cap.
- `square_off` — no new entries after this IST time; open position is force-flat.
- **Kill switch** — create a file named `KILL` in this folder (or press **Force-Flat**
  in the dashboard) to immediately flatten and stop entering.

---

## The default strategy — TrendPulse

Fully described in `teji/strategy/trend_pulse.py`. In one line:

- **LONG** when EMA(9) is above EMA(21) **and** price is above VWAP.
- **SHORT** when EMA(9) is below EMA(21) **and** price is below VWAP.
- **EXIT** when the fast/slow EMAs flip against the position; plus an ATR-based
  stop-loss and a reward:risk target, and a re-entry cooldown after each exit.

Swap in your own logic by implementing the same `evaluate()` contract — return a
`Decision` with `action`, a human `reason`, and the `conditions` list. Everything
downstream (risk, execution, dashboard) is strategy-agnostic.

---

## Where this runs

Not in an ephemeral cloud sandbox — a live trader needs a **persistent** process.
Run it on your own machine or a small always-on VPS during market hours. Keep the
dashboard bound to `127.0.0.1` (default) unless you deliberately secure it.

## Compliance

Under SEBI's retail-algo framework your broker tags API orders as algo and applies
rate limits. TEJI trades on candle closes (very low order rate) and caps trades per
day, which keeps it well inside retail bounds — but you are responsible for staying
compliant with your broker's and SEBI's current rules.

## Known limitations / TODO (be honest with yourself before live)

- **Fill price reconciliation.** Live fills currently reference LTP; a follow-up
  should read the order/trade book for the true average fill and update P&L.
- **Reconnection & token rollover.** The WebSocket has basic status callbacks but no
  auto-reconnect/backoff yet; SmartAPI session tokens also expire daily.
- **SmartAPI field names** shift between SDK versions — the first live tick prints
  its keys so you can confirm `last_traded_price` / `volume_trade_for_the_day`.
- **Costs** (brokerage, STT, GST, slippage beyond the flat bps) aren't fully modelled
  in paper P&L — see the companion `sauda.html` for the real Indian cost stack.
- No backtester yet; this validates *forward* on live/paper. A historical backtest is
  the obvious next module.

## Disclaimer

For education and personal use. Derivatives can lose you more than you invest. No
warranty. You are solely responsible for any orders this software places on your
account.
