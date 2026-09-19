# BTC15M Web V2.16 — Profit Protection + Reliable Rollover

V2.16 is the web successor to V2.15. The underlying chart/decision research remains V10.31 except for web/live-engine rollover reliability changes.

## Changes

1. API JSON hardening
   - `/api/state` and `/api/health` always return JSON on application errors.
   - Browser validates HTTP status and `Content-Type` before parsing JSON.
   - Up to 3 short retries on transient failures.
   - Last valid dashboard remains on screen while status shows `DATA RETRY`.
   - Prevents intermittent `<!doctype ... is not valid JSON` parsing errors from replacing dashboard state.

2. Continuous display chart
   - Browser chart receives an exact 90-slot 1-minute UTC display grid ending on the current minute.
   - Missing display minutes are flat carry-forward candles.
   - The current BRTI is attached to the newest display candle to remove the live right-edge gap.
   - This is display-only. Synthetic chart candles never enter the trained model, Chart Signal, Decision, MP, RSI, KDJ, MACD, TR, FLIP, or OF logic.

3. Manual position tracking removed
   - Removed trade-side selector, max entry, actual fill, contracts, Enter/Close buttons, P&L input workflow, save snapshot, and journal export UI.
   - Kalshi YES/NO bid/ask remains visible for execution context only.

4. Automatic Trade Decision / entry quality
   - Uses the current Market Decision side automatically.
   - Scores executable ask plus agreement/quality context from Chart, MP, fusion, price-confirmed OF, exhaustion, and reversal state.
   - Labels: EXCELLENT ENTRY, GOOD ENTRY, FAIR / WAIT, WAIT, or DON'T CHASE.
   - Kalshi prices do not alter Chart Signal or Market Decision.

5. Profit protection / exit lifecycle
   - A browser-local virtual reference arms automatically when entry quality first becomes GOOD or EXCELLENT.
   - No manual fields are required or shown.
   - Tracks decision-side executable bid, peak bid, current profit, peak profit, and giveback.
   - States: HOLD — DEVELOPING, PROFIT AVAILABLE, PROTECT PROFIT, TAKE PROFIT.
   - Exit becomes more aggressive when profit exists and there is peak giveback, FLIP activity, Market Decision flip, reversal confirmation, MP opposition, exhaustion, adverse OF response, or late-contract risk.
   - Does not require holding until settlement or waiting for full reversal confirmation.
   - Exit alerts remain displayed briefly after firing so they are visible to the user.

### Current V2.16 heuristic protection thresholds
These are execution heuristics for live testing, not claimed as historically optimized final thresholds.

- Profit becomes available after peak executable profit >= 5¢.
- Protection can arm after peak profit >= 8¢.
- Protect on giveback >= max(3¢, 20% of peak profit), or when current profit >=3¢ and deterioration risk appears.
- Take profit on giveback >= max(5¢, 32% of peak profit) once peak profit >=8¢.
- Take profit immediately while profitable on a new FLIP, Market Decision flip, or confirmed reversal.
- Take profit when peak profit >=15¢, current profit >=7¢, and at least two deterioration risks are present.
- Take profit with <=45 seconds remaining if current executable profit is >=8¢.
- Exit if a trade previously reached >=8¢ peak profit and current profit falls to <=1¢.

6. Rollover V2.16
   - Computes deterministic next KXBTC15M ticker.
   - Starts direct prefetch 90 seconds before current expiry.
   - Retries exact ticker lookup every 1 second before expiry.
   - Uses broad discovery every 5 seconds only as fallback.
   - At expiry, prefetched contract switches immediately without rejecting it for a slightly delayed `open_time` timestamp.
   - If not prefetched, exact expected ticker is retried every ~350 ms during rollover; broad active-market discovery remains fallback.
   - UI shows PRELOADING/READY and rollover mode/latency.
   - Diagnostics include expected ticker, prefetch start, attempts, market found, target loaded, rollover mode, latency, and fallback use.

## Deployment layout

Copy the contents of this folder directly to the Git repository root:

```
Dockerfile
app.py
live_btc15m_predictor.py
live_model_bundle.joblib
requirements.txt
static/index.html
...
```

Do not upload `.pem`, `.env`, API keys, or any secrets.

Recommended deployment commit:

```
git add -A
git commit -m "Deploy V2.16 profit protection and reliable rollover"
git push origin main
```

After Render finishes, hard refresh the browser with Ctrl+F5.
