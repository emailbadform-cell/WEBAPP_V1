# V2.24.5 / V10.35 Release Validation

## Changes validated
- Web Decision continues to use `decision_signal_model.joblib` through `SignalSuite.decision_state`; Current Side is display/reference only.
- V10.35 research logger now writes `predictive_decision`, probability/confidence/role, and uses that value for the `decision` field. Legacy current side is separately retained as `legacy_current_side_reference`.
- MP completion progress remains 0–100%; signed progress and adverse-from-anchor are added. Web UI displays negative progress during adverse movement instead of appearing frozen at 0%.
- Rollover/prefetch adds exact expected-ticker lookup through the KXBTC15M series listing, 2s pre-expiry fallback discovery, exact-ticker `DIRECT-LIST` handoff, and 0.5s final broad fallback.
- Candle2 remains calculated/logged for research but is not rendered on the chart.
- Duplicate Forward diagnostics group remains absent; main Forward tile remains.
- TR, FLIP/RE-FLIP, Forward models/thresholds, GT rules, L2/OF authority, and Profit Protection thresholds unchanged.

## Validation
- Python compile: PASS
- Browser JavaScript syntax (`node --check`): PASS
- Deterministic next-ticker regression: PASS (`05:45Z` -> `KXBTC15M-26SEP130200-00`)
- Predictive Decision smoke test: PASS; test case produced a Decision different from factual Current Side, proving the logger is no longer mechanically current-side anchored.
- MP adverse-movement regression: PASS; completion stays 0% while signed progress becomes negative and adverse distance increases.
- Forward diagnostics ID scan: PASS
- Candle2 chart-render code scan: PASS
- Secret file scan (`.pem`, `.key`, `.env*`): PASS

## Important interpretation
The V10.34 zero MP Progress observations were predominantly adverse movement behind the projection anchor, not positive movement toward Base. V10.35 therefore preserves mathematically correct 0% completion and adds signed/adverse state rather than falsely counting adverse movement as completion.
