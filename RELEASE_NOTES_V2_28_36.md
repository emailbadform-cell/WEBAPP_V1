# BTC15M Web V2.28.36

Runtime correctness + fast rollover update based on V2.28.35.

- Preserves validated V2.28.35 atomic cumulative RDFZ exporter unchanged.
- Propagates `prev_m1_trend` and `macd_hist_velocity` into runtime prediction state so frozen Trend Transition V2 can actually ARMED/TRIGGERED.
- Adds `trend_transition` to prospective architecture RDFZ snapshots.
- Fixes predictive Decision research path referencing undefined `preserved_seconds`; it now uses the supplied causal tick history.
- Adds a dedicated background Kalshi market-stream synchronization worker so current/expected-next subscriptions do not depend on page/API rendering cadence.
- Uses WS evidence for the deterministic expected-next ticker as an existence hint only; Kalshi market price remains excluded from prediction architects.
- Keeps expected-next subscription awareness up to 300s early, starts aggressive exact metadata resolution inside 90s (or immediately when WS evidence exists), and limits broad discovery to the final 30s/fallback path.
- Corrects prospective architecture filename/version labels to V10.39.21 / V2.28.36.
- Production Decision/Settlement/GT/TR/Flip/Auto Paper policy mathematics are unchanged.

Validation: Python compile PASS; candidate tests PASS; multi-contract Forced Coverage PASS; Transition V2 ARMED/TRIGGERED regression PASS.
