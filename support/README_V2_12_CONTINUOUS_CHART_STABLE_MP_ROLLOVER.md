# Web V2.12 / Core V10.28

Changes from V2.11:
- Fixes visible BRTI chart gaps at the presentation layer by reindexing the recent 90-minute display to complete 1-minute slots and rendering missing historical slots as flat carry-forward candles.
- The model's original candles are untouched; the chart-gap repair does not alter Chart Signal, MP, TR, or Decision features.
- Adds V10.28 5-second MP direction-change confirmation to reduce projection churn while preserving immediate Base rearm.
- Adds deterministic next-contract direct lookup before broad discovery to improve rollover prefetch.
- Keeps Validated OF research-only; no same-sample weight re-optimization after the latest forward block.
