# Web V2.28.18 — Event-Driven Kalshi Execution Data

- Kalshi authenticated WebSocket is now primary for current + prefetched-next orderbook, ticker, and public trades.
- Snapshot + sequence-checked orderbook deltas; sequence gaps mark the book unhealthy and force reconnect/resnapshot.
- REST orderbook retained strictly as recovery/fallback.
- Backend state construction wakes on Kalshi market events with 50 ms coalescing and a 750 ms watchdog ceiling.
- Browser receives state-change SSE; 5 s REST polling remains watchdog fallback.
- Auto Paper V1 rules and all prediction authority are unchanged.
- Execution telemetry adds quote age, depth, sequence, stream health, reconnects, and sequence-gap counts.
- Current + deterministic/prefetched next KXBTC15M contracts are warmed concurrently.
