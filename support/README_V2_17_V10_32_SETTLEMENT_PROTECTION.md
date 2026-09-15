# BTC15M Web V2.17 / Research V10.32

V2.17 integrates the V10.32 settlement/reversal research layers into the V2.16 web app without changing the Chart Signal or Market Decision architecture.

## Added
- Settlement Protection: PROTECTED / MODERATE / OPEN-VULNERABLE from existing TR status, with contract-deduplicated historical reference counts shown as descriptive context only.
- Target-Cross Hazard: 30s / 60s / 120s / 300s / full remaining-time cross estimates using the frozen TR geometry/calibration.
- Profit-Reversal Risk: progressive 0–100 deterioration score, level, action candidate, and evidence list.
- Profit protection now treats V10.32 ELEVATED/HIGH risk as an additional profit-defense input while retaining V2.16 giveback, FLIP, Decision-flip and confirmed-reversal rules.

## Preserved
- V2.16 continuous 90-minute display-only gap fill.
- Chart/Decision separation and Kalshi-price execution-only rule.
- Existing entry-quality calculation.
- Existing deterministic prefetch/direct rollover implementation and diagnostics.
- JSON-only API error handling and browser retry behavior.

## Research caution
Historical reference rates are observed contract-level results, not guaranteed probabilities. V10.32 risk scores are research heuristics, not calibrated probabilities and not automatic exchange orders.
