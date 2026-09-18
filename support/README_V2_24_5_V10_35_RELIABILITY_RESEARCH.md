# BTC15M Web V2.24.5 / Research V10.35

Reliability/research update after V10.34 validation.

- Web Decision remains the predictive no-current-side model (`decision_signal_model.joblib`).
- Research logger retires the legacy current-side value as a Decision; it is retained only as `legacy_current_side_reference`.
- MP now records signed progress and adverse distance from the projection anchor; completion progress remains 0..100. The UI shows negative progress during adverse movement instead of appearing frozen at 0%.
- Rollover adds exact expected-ticker lookup through the KXBTC15M series listing, faster prefetch fallback, and exact-ticker rollover before broad discovery.
- Candle2 remains calculated/research-only but is no longer drawn on the main chart.
- Forward diagnostics card remains absent; main Forward tile remains. Internal Forward reversal phase remains logged.
- TR, FLIP/RE-FLIP, Forward thresholds/models, GT rules, L2/OF authority, and Profit Protection thresholds are unchanged.
- No Kalshi YES/NO prices are used by Chart/Forward/Decision.
