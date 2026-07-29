# TEJI Desk — a transparent, live-data intraday trading engine (Indian markets)

TEJI Desk streams **live** market data, runs a **transparent** rule-based strategy
across a **watchlist of instruments at once** — Nifty, Bank Nifty, stocks, **and
Bitcoin/Ethereum in ₹** — and shows you, on a live dashboard, each running position
and the *exact logic* behind every buy and sell.

It is **paper-first by design**: real prices in, real signals, real reasoning,
but **simulated fills** until you deliberately switch to live orders. Nothing here
invents prices except the offline `mock` feed, which is labelled as such everywhere.

**Everything is decidable in the app** — switch the candle timeframe (1m / 5m /
15m / 1h), toggle any instrument's trading on/off, trade the whole watchlist or
just one, and flatten everything — all live, no restart.

### Markets & feeds
| Asset | Feed | Live data | Live orders |
|---|---|---|---|
| Nifty / Bank Nifty / stocks / F&O | **Angel One SmartAPI** | needs your API login | supported (gated) |
| **Bitcoin / Ethereum (₹)** | **CoinDCX public ticker** | **no account needed** | needs a crypto-exchange adapter (TODO) |
| anything, offline | `mock` synthetic feed | — | — |

> **This is engineering scaffolding, not investment advice, and not a money
> machine.** A strategy that executes cleanly is *not* the same as a strategy that
> is profitable. The default strategy (TrendPulse) is a well-known, deliberately
> simple example so you can see the machinery working — the edge is yours to build.

---

## What you get

```
 Feeds (per instrument):  Angel One WS  ·  CoinDCX ticker  ·  mock
        │  each tick routed by symbol
        ▼
  Trader (one per instrument)
     Candle aggregator ──► Indicators (EMA fast/slow, VWAP, ATR)
        │
        ▼
     Strategy (TrendPulse) ──► Decision { action, reason, conditions… }  ← the "why"
        │
        ▼
     Risk (size, portfolio daily max-loss, square-off, kill-switch, enable/disable)
        │
        ▼
     Execution:  Paper (simulated on live price)  |  Angel One (REAL orders, gated)
        │
        ▼
  Live dashboard  (per-instrument position · live decision · execution log
                   + timeframe switch, on/off toggles, trade-all, flat-all)
```

Every trade is recorded **with the conditions that produced it**
(e.g. `EMA9 above EMA21 ✓`, `Price above VWAP ✓`) and every exit records *why*
(`target hit`, `stop-loss hit`, `square-off`, `trend flipped`).

### In-app controls (no restart, no editing files)
- **Timeframe** — 1m / 5m / 15m / 1h buttons; changing it rebuilds every
  instrument's candles and re-warms the strategy.
- **Per-instrument on/off** — the `ON/OFF` toggle on each rail card decides whether
  that symbol may take trades. Disabled instruments still stream and still manage an
  open position to the exit — they just won't open new ones.
- **Trade-all / Pause-all** and **Flat-all** (kill switch) in the header.

---

## Run it right now (no account needed)

Requires Python 3.10+.

```bash
cd teji-desk
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # PyYAML alone is enough for the mock feed
python run.py --mock
```

Open **http://127.0.0.1:8899**. You'll see the whole watchlist (Nifty, Bank Nifty,
a stock, BTC, ETH) running on a synthetic feed: candles form, TrendPulse takes
paper positions per instrument, and the execution log fills with reasoning. Play
with the timeframe buttons and the on/off toggles — this is the exact UI you'll use
with live data; only the price source changes.

### Add live crypto with zero setup
BTC/ETH already use the **CoinDCX public ticker**, so as soon as you're online they
price in real ₹ with **no account** — in paper mode. Just run without `--mock` (or
run `--live-data`); the crypto instruments go live while equities wait for your
Angel One login.

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
- **Live crypto orders.** BTC/ETH are live-data + paper only; real crypto orders
  need an authenticated CoinDCX / Delta Exchange India adapter (HMAC-signed) — the
  `Execution` interface is ready for it, it just isn't written yet.
- **Costs** (brokerage, STT, GST, slippage beyond the flat bps) aren't fully modelled
  in paper P&L — see the companion `sauda.html` for the real Indian cost stack.
- No backtester yet; this validates *forward* on live/paper. A historical backtest is
  the obvious next module.

## Disclaimer

For education and personal use. Derivatives can lose you more than you invest. No
warranty. You are solely responsible for any orders this software places on your
account.
