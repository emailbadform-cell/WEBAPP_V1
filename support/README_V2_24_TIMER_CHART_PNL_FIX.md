# BTC15M Web V2.24 / V10.34 — Timer, Chart Hardening, Clear Live P/L

V2.24 is a browser/UI reliability update on top of V2.23. Predictive and research model files are unchanged.

## Changes

- TIME LEFT now uses the contract `close_time` as an absolute browser-side expiry anchor and redraws every 200 ms. API refresh cadence no longer directly drives the visible countdown.
- On contract change, the expiry anchor is replaced immediately. At local zero, the browser requests an immediate state refresh; settlement/rollover authority remains with the existing market/session logic.
- GT projected prices are rejected if zero, non-finite, negative, malformed, or implausibly far from live BRTI.
- Candle2 provisional opens receive the same validation.
- GT overlay values cannot independently force chart autoscaling toward zero or another extreme.
- The base chart range comes from valid real candles plus a sane Kalshi target. GT may expand that range only within guarded limits.
- If a transient GT/MTF state is invalid, that overlay is skipped for that render cycle instead of corrupting the chart.
- Tracked Trade now shows a large green/red LIVE P/L for the active $100 paper position.
- After a trade closes, the same field displays LAST REALIZED P/L until the next trade begins.

## Architecture unchanged

Forward Signal, Decision, GT prediction logic, MP, TR, OF/L2 authority, FLIP/RE-FLIP, execution pricing, paper-trade sizing, and V10.34 research logging are unchanged.
