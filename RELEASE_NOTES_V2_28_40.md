# BTC15M Web V2.28.41 — Kalshi Final Target Primary

- Subscribes to authenticated Kalshi `cfbenchmarks_value` for BRTI alongside the existing 5Hz BRTI feed.
- Uses `last_60s_windowed_average_15min.value` as the primary Final Target during the final minute.
- Displays/logs Kalshi `window_size` and window timestamps.
- Retains the local source-timestamp 60-second accumulator as an independent verifier/fallback.
- Logs Kalshi-minus-local discrepancy for audit.
- Does not feed Kalshi market prices into Decision, Settlement, or GT.
- Existing V2.28.39 reconstructed expiry accounting remains as fallback until official result ingestion is separately validated.
- Frozen Primary Auto Paper gates unchanged.
