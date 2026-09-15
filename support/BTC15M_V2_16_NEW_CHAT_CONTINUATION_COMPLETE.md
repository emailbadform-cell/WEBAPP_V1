# BTC15M / Kalshi New-Chat Continuation — V2.16 Complete

Use this file to resume the BTC 15-minute Kalshi project in a new ChatGPT conversation.

## Objective
The app predicts whether BRTI/BTC will finish ABOVE or BELOW the Kalshi KXBTC15M target at the end of a 15-minute contract. Kalshi target and expiry define the contract. BRTI/chart data drive Chart Signal and Decision. Kalshi YES/NO prices must never alter Chart Signal or Market Decision; they are execution context only.

## Current web version
**V2.16 / V10.31**

Web package:
`BTC15M_WEBAPP_V2_16_PROFIT_PROTECTION_ROLLOVER_COMPLETE.zip`

V2.16 supersedes V2.15 for website deployment.

## Current architecture
1. Chart Signal — chart-only direction/probability; target distance excluded.
2. Decision Signal — settlement decision anchored to current BRTI side vs target.
3. Target Reachability — separate calibrated distance/time/volatility diagnostic.
4. Move Projection — chart-only directional continuation/projection lifecycle.
5. Multi-exchange Order Flow — research/context, not a silent Chart override.
6. OF Early, OF Micro, OF→Price Response, MP+OF context, Decision Fusion.
7. FLIP / RE-FLIP — target-crossing research.
8. RSI14, KDJ J 9/3/3, MACD 12/26/9 — display/research context.
9. Exhaustion/Reversal — research-only context from V10.31.
10. Trade Decision — V2.16 automatic entry quality on the Market Decision side.
11. Profit Protection — V2.16 browser-local virtual execution reference and profit-aware HOLD/PROTECT/TAKE PROFIT lifecycle.
12. Rollover — V2.16 proactive deterministic next-contract prefetch and direct handoff.

## Important model rules
- Chart Signal remains independent of target distance and Kalshi market prices.
- Decision remains current-side anchored.
- Kalshi order book is execution-only.
- Display gap-fill candles are visual only and never enter model features.
- Do not claim 100% future accuracy. Historical perfect subsets should be described as “100% observed on qualifying sample” with sample size.

## FLIP / RE-FLIP
Initial FLIP arm: calibrated TR >=60%, no fixed dollar ceiling. Exact reconstruction previously observed 23/23 qualifying complete contracts cross, with farthest first qualifying observation about $33.74.

Operational RE-FLIP subset: after an actual target cross, first observation >=1 second later, distance <=$5, calibrated TR >=90%, and movement has not gone farther away from target than the cross print. Observed 53/53 development + 13/13 later-forward = 66/66 qualifying events. This is historical observation, not a guarantee.

## V2.16 changes

### 1. Intermittent invalid-doctype / non-JSON fix
The browser previously occasionally tried to parse an HTML error page beginning with `<!doctype html>` as JSON.

V2.16:
- validates response status and content type;
- retries transient `/api/state` failures up to 3 times;
- preserves last valid dashboard state while showing DATA RETRY;
- API endpoints return JSON error objects instead of HTML application errors;
- generic `/api/*` exceptions are returned as JSON.

### 2. Continuous chart
V2.16 constructs an exact 90-minute display grid ending at the current UTC minute. Missing display minutes are flat carry-forward candles. The current BRTI is explicitly attached to the newest candle so the live right edge does not separate from chart history.

This is display-only. Engine/model candles remain unchanged.

### 3. Manual position form removed
Removed:
- Trade side selector
- Max entry price
- Actual entry price
- Contracts
- Enter position
- Close position
- manual P&L position field
- Save snapshot
- Export private journal controls

### 4. Automatic Trade Decision / entry quality
The app automatically scores the current Market Decision side using the executable Kalshi ask plus setup context.

Entry labels:
- EXCELLENT ENTRY
- GOOD ENTRY
- FAIR / WAIT
- WAIT
- DON'T CHASE

The score currently combines:
- executable ask price quality;
- Chart agreement with Decision;
- MP direction and strength;
- Decision Fusion state;
- MP+OF price continuation/opposition;
- exhaustion level;
- reversal development/confirmation.

These are V2.16 live execution heuristics and should be researched further rather than treated as frozen optimal thresholds.

### 5. Profit-aware exit engine
The old V2.15 exit logic waited too long for exhaustion/reversal and frequently never produced an exit. V2.16 changes the objective from “hold until proven reversal” to “protect executable profit before a FLIP/reversal can erase it.”

When entry quality becomes GOOD or EXCELLENT, the browser automatically arms an internal virtual reference using the decision-side ask. No user position fields are shown.

The app tracks:
- reference entry ask;
- current executable decision-side bid;
- peak executable bid;
- current profit in cents;
- peak profit in cents;
- giveback from peak;
- FLIP count since reference entry;
- deterioration context.

Profit states:
- HOLD — DEVELOPING
- PROFIT AVAILABLE
- PROTECT PROFIT
- TAKE PROFIT

Current V2.16 heuristic thresholds:
- Profit available: peak profit >=5¢.
- Protection can arm: peak profit >=8¢.
- Protect if giveback >= max(3¢, 20% of peak profit), or current profit >=3¢ with deterioration risk.
- Take profit if giveback >= max(5¢, 32% of peak profit) after peak profit >=8¢.
- Take profit immediately while profitable on Market Decision flip, a new FLIP after reference entry, or confirmed reversal.
- Take profit if peak profit >=15¢, current profit >=7¢, and at least two deterioration risks are present.
- Take profit with <=45 seconds left if current profit >=8¢.
- Exit if peak profit was >=8¢ and current profit falls to <=1¢.

Deterioration risks include developing reversal, exhaustion >=65, MP opposing reference side, adverse/absorbed OF price response, MP+OF price opposition, and MP PROTECT/CASH action.

Exit alerts are held briefly after firing so the user can actually see them.

Future research priority: optimize giveback thresholds and measure Profit Capture Ratio, MFE, and MAE from real execution snapshots rather than assuming current heuristics are optimal.

### 6. Reliable next-contract rollover
Previous deterministic prefetch still failed in live use.

V2.16 rollover behavior:
- calculates the exact expected next KXBTC15M ticker;
- begins prefetch 90 seconds before expiry;
- direct exact-ticker lookup every 1 second;
- broad next-market discovery every 5 seconds as fallback;
- if next contract is prefetched, switches immediately at expiry without requiring upstream `open_time` to already be <= current time;
- if not prefetched, direct expected-ticker retry every ~350 ms after expiry;
- broad active-market discovery every ~800 ms only as fallback;
- resets MP/FLIP/OF-response trackers on contract switch.

Rollover diagnostics exposed to UI:
- next_ticker_expected
- next_prefetch_started
- next_prefetch_attempts
- next_market_found
- next_target_loaded
- rollover_mode
- rollover_latency_ms
- fallback_discovery_used

UI shows `PRELOADING · <ticker>` or `READY · <ticker>` before expiry.

## BRTI / Kalshi
Production Trade API base:
`https://external-api.kalshi.com/trade-api/v2`

BRTI current REST:
`GET /cfbenchmarks/values?id=BRTI`

BRTI primary live feed uses Kalshi `cfbenchmarks_value_5hz` WebSocket; REST fallback activates when stale.

Public execution orderbook:
`GET /markets/{ticker}/orderbook`

YES/NO bid/ask data is execution-only.

## Deployment
Repository root should contain `Dockerfile`, `app.py`, `live_btc15m_predictor.py`, `live_model_bundle.joblib`, `requirements.txt`, and `static/index.html` directly.

Local repo previously used:
`C:\BTC\BTC RENDER GIT`

Deploy V2.16 after copying the **contents** of the extracted `v216` folder into the repo root:

```bat
cd /d "C:\BTC\BTC RENDER GIT"
git add -A
git status
git commit -m "Deploy V2.16 profit protection and reliable rollover"
git push origin main
```

Never commit `.pem`, `.env`, Kalshi API keys, or secrets. Render may hold the private key as a secret file at `/etc/secrets/kalshi_private_key.pem`.

After deployment, use Ctrl+F5 for a hard refresh.

## Validation already performed on V2.16 package
- Python compile check for `app.py` and `live_btc15m_predictor.py`.
- Frontend JavaScript syntax check using Node.
- Static DOM-reference check: all JavaScript `$('<id>')` references resolve to existing HTML IDs.
- Mock `build_state()` chart continuity test: exactly 90 display candles generated and latest candle close matches live BRTI.
- Deterministic ticker sanity check across known timestamps.

## Next validation priorities
1. Observe at least several real contract rollovers and verify READY before expiry and PREFETCH/DIRECT rollover without stale old ticker.
2. Record whether chart displays any visible missing minute/right-edge gap after V2.16.
3. Observe real GOOD/EXCELLENT entry windows and confirm profit states transition during favorable moves.
4. Collect actual entry-quality / orderbook / peak-bid / exit-signal sequences for MFE, MAE, giveback, and Profit Capture Ratio research.
5. Optimize profit-protection thresholds on chronological holdout data; do not tune and score on the same events.
6. Verify no intermittent HTML/non-JSON API parsing errors; if one occurs, capture endpoint/status/content-type rather than suppressing it.

## User preference for this project
Be direct and practical. Give exact conditions and numbers when available. Preserve strict chronology in testing. Do not silently change Chart/Decision architecture when modifying execution/UI logic. Do not create a new version unless explicitly requested.
