# V10.32 — Settlement Protection / Target-Cross Hazard / Profit-Reversal Risk

V10.32 preserves the existing Chart Signal, current-side Market Decision, V10.19 calibrated Target Reachability, FLIP/RE-FLIP, Move Projection, and order-flow architecture. It adds research-only layers derived from the V10.31 contract-level validation. None of these new layers may silently override Chart Signal or Market Decision.

## New research layers

### Settlement Protection
Uses the existing TR status as a separate settlement context. Historical contract-deduplicated V10.31 references are stored only as descriptive evidence, not as guaranteed live probabilities:
- TR UNLIKELY: 34/43 current-side settlements correct (79.1% observed)
- TR MARGINAL: 30/43 (69.8% observed)
- TR LIKELY REACHABLE: 22/40 (55.0% observed)

The layer reports PROTECTED / MODERATE / OPEN-VULNERABLE. It does not change Decision.

### Target-Cross Hazard
Produces research estimates for target-cross probability within 30s, 60s, 120s, 300s, and full remaining time. It reuses the frozen V10.19 distance/ATR/time geometry and calibration at each shorter horizon. This is intentionally separate from Chart direction and settlement Decision.

### Profit-Reversal Risk
Adds a progressive 0–100 research score and action candidate. Evidence hierarchy follows V10.31 testing:
- CONFIRMED reversal: strongest short-horizon executable-price danger signal.
- New target FLIP: high-value early danger event, but FLIP remains fundamentally a target-cross mechanism.
- MP opposition, Fusion conflict, Chart/Decision disagreement, MP+OF opposition: earlier but weaker deterioration evidence.
- DEVELOPING reversal: warning only.
- Exhaustion alone: context only; it is not promoted to an exit trigger.

The score is a research heuristic, not a calibrated probability and not an automatic order instruction.

## New log
`BTC15M_V10_32_REVERSAL_SETTLEMENT_RESEARCH_LOG.csv`

Added fields include settlement protection state/reference, target-cross hazard ladder, profit-reversal score/level/action candidate, and the component reasons. The original V10.31 log is retained as historical source data.

## Validation utility
Run `ANALYZE_V10_32_REVERSAL_SETTLEMENT.bat` or:

`python analyze_v10_32_reversal_settlement.py`

The analyzer deduplicates settlement studies at the contract level and measures executable Decision-side bid deterioration at 10/30/60 second horizons. This is designed to reduce the false confidence caused by treating highly correlated snapshots as independent trials.

## Security
No Kalshi private key is included in the V10.32 package. Keep `.pem`, `.env`, API keys, and other secrets outside research/deployment archives and source control.
