# V2.28.45 — Retryable KXBTC15M Initialization / Target-Pending Fix

- Fixes startup failure when the deterministic current KXBTC15M ticker exists but Kalshi has not yet published its strike/target.
- Distinguishes `TICKER_FOUND_TARGET_PENDING` from a genuinely unresolved current contract.
- Changes current-contract discovery gaps into retryable `WAITING_FOR_CURRENT_KXBTC15M` state.
- Background engine remains alive and retries discovery every second instead of terminating with `Initialization failed`.
- Prediction begins normally as soon as a valid target is available.
- No changes to GT-C, GT-B, Decision, Settlement, Auto Paper authority, or GT chart visual sequence.
