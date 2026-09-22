# BTC15M Web V2.28.41 — Current Problems Repair

- Kalshi CF Benchmarks is the sole Web Final Target display authority. Local 60-second reconstruction remains diagnostic only.
- Final Target UI identifies KALSHI FINAL TARGET and shows Kalshi window_size/feed age.
- Kalshi execution WebSocket subscriptions compare membership rather than caller order, preventing needless reconnects.
- Completed/stale contract books, tickers, trades, and SID sequence state are pruned whenever desired markets change.
- RDFZ status/export-list browser calls validate HTTP status/content type and report useful API errors instead of JSON `<!DOCTYPE` SyntaxErrors.
- Added `/api/runtime/health` for no-shell diagnostics: peak RSS, disk usage, BRTI feed health, state-build timing, and Kalshi WS health.
- Frozen Decision, Settlement, GT1–GT15, TR, Flip and Auto Paper Primary policy logic are unchanged.
