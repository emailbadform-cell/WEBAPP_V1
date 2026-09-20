# BTC15M Web V2.18 / Research V10.32

V2.18 is a chart-stability and visualization update built on V2.17. It does not alter Chart Signal, Market Decision, Target Reachability, FLIP/RE-FLIP, MP, order-flow scoring, entry-quality scoring, or V10.32 settlement/profit-risk logic.

## Chart continuity changes

- Retains the server-side exact 90-minute display-only 1-minute grid.
- Retains carry-forward display candles for missing display minutes; these synthetic display candles never enter model features.
- Keeps the current BRTI attached to the newest displayed candle.
- Adds a browser-side stabilization layer that merges the newest valid chart payload with the prior valid 90-minute chart instead of replacing the chart with a transient partial/empty payload.
- Invalid OHLC rows are ignored without clearing the prior valid chart.
- The displayed sparkline is regenerated from the stabilized candle series so candle and line modes stay aligned.

## EMA overlays

- Adds EMA 9 and EMA 21 directly over the candle chart.
- Current EMA 9 and EMA 21 values are shown above the chart.
- Cross status shows `9 ABOVE 21`, `9 BELOW 21`, or `NEAR CROSS`.
- EMA overlays are display-only and do not change any trading signal or research architecture.
- The server includes display EMA values calculated from the continuous displayed close series; the browser has a local fallback calculation for compatibility.

## Important

The EMA overlays are intended to help visually identify potential 9/21 crosses. They are not standalone trade signals and do not silently override Chart Signal or Market Decision.
