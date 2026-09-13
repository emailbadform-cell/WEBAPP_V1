# BTC15M Web V2.23 / V10.34

Base: V2.22 / V10.34.

## Changes
- Manual TAKE TRADE UP / TAKE TRADE DOWN entries are fixed $100 paper positions.
- Entry uses the selected side ask; manual exit uses the selected side bid.
- Contract expiry settles the paper position to $1.00 on a winning side or $0.00 on a losing side.
- Session Earnings accumulates realized P/L only for the current Kalshi contract and resets on confirmed ticker rollover.
- Total Earnings persists in browser localStorage across contracts and page refreshes.
- Completed paper trades and completed-session totals are retained in browser localStorage for reconstruction/audit.
- GT projected candles render white; the on-chart GT / GT+1 text labels are removed.
- GT Candle #2 remains lower-opacity than the primary projected candle.
- GT Line begins at the next candle slot instead of on top of the current candle.
- GT display carries across 1m / 5m / 10m / 15m chart views without changing the underlying GT forecast state.
- BRTI feed age remains right-aligned; no LIVE word beside BRTI.
- Existing right-side chart price axis and live BRTI price marker remain.

## Important behavior
This is paper accounting only. The $100 stake, Session Earnings, Total Earnings, and trade ledger do not feed Forward, GT, Decision, TR, MP, OF, L2, FLIP/RE-FLIP, or settlement prediction logic.

GT on higher chart timeframes is the same short-horizon GT forecast mapped visually to the selected chart; it is not a new 5m/10m/15m predictive model.
