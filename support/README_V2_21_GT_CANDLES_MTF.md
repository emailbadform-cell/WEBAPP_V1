# BTC15M Web V2.21 / Research Context V10.34

## Purpose
V2.21 is a web/UI + Ghost Thread lifecycle update built from V2.20. It does not change the frozen unrelated Chart, TR, MP, OF, FLIP/RE-FLIP, settlement-protection, or profit-protection core functions.

## Changes
- Adds chart display selector: **1m / 5m / 10m / 15m**.
- The server now supplies up to 360 minutes of display-only 1m candles so higher display timeframes have useful history.
- 5m/10m/15m candles are browser-side display aggregation only and do not feed any model.
- Default GT display is now **projected candles** instead of a line.
- GT display selector: **GT Candles / Line / Off**.
- GT projected candle #1 represents the probabilistic completion state of the active 1m candle using the fixed 1m open + GT lifecycle direction.
- Conditional **GT+1** preview is drawn only when the existing Candle #2 T+50 preliminary gate is active.
- Candle #3 remains disabled.
- Adds stateful GT direction anti-flicker: two consecutive contrary GT proposals are required before repainting the projected candle within the active minute.
- Existing Forward horizon hysteresis remains: two confirmations to extend, one failure to contract.
- 1m fixed-open lifecycle remains: Forward early, then actual BRTI/open displacement increasingly dominates, with persistence dominant late.
- 2m/3m/4m/5m GT structural/event states remain context only; they do not mechanically override 1m direction.

## Projected candle semantics
Projected candles are **visual probability/uncertainty objects**, not exact future OHLC predictions. The body direction comes from GT lifecycle state. Body/wick size is a bounded visualization derived from current displacement, Forward confidence, and GT uncertainty. Do not interpret the displayed projected high/low/close as exact dollar forecasts.

GT projected candles are rendered only in **1m chart mode** because the validated GT lifecycle is a 1m fixed-open architecture. On 5m/10m/15m chart modes, GT projection is intentionally suppressed rather than implying an unvalidated higher-timeframe future candle forecast. The legacy GT line can still be selected for comparison in 1m mode.

## Preserved architecture
- Kalshi YES/NO prices do not influence Forward or predictive Decision.
- Predictive Decision remains no-current-side architecture.
- MP remains independent of OF/L2.
- L2 remains display/research context only with no direct authority over Forward, Decision, GT, TR, or MP.
- Manual trade tracking remains browser-local and places no Kalshi orders.

## Deployment
Render deployments connected to GitHub auto-deploy after pushing the updated files to the configured branch.
