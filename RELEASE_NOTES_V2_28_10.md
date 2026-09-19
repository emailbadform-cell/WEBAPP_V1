# V2.28.10 realized GT slot replacement

Corrects GT realization semantics.

- The two original BRTI 1m context candles remain frozen.
- The two visual gap slots remain fixed.
- GT1-GT15 retain fixed positions.
- Each GT slot is white/projected until its corresponding BRTI 1m candle is fully complete.
- Once complete, that exact GT slot is replaced with the actual BRTI OHLC candle and rendered green/red.
- Realized GT slots remain actual; later GT slots remain live recursive projections.
- Contract start is derived from the KXBTC15M close time (close minus 15 minutes), so refreshing the page mid-contract does not reset GT1 timing.
- No Decision, Settlement, OF/L2, forecast-generation, startup, BRTI-feed or contract-discovery logic changed.
