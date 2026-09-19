# BTC15M Web V2.28.30

## Changes
- Fixed Final Target (Est.) collection with a persistent per-contract source-timestamp-second accumulator.
- Final Target uses the 60 seconds immediately preceding contract close and retains one last-tick observation per source second.
- Fixed Final Target card layout so value/status/diagnostics do not overlap.
- Added real deduplicated SHADOW_REJECTED hypothetical trades with entry, exit, P&L, MFE/MAE and failed-gate attribution.
- Preserved frozen PRIMARY Auto Paper gates and exit logic.
- Added separately labeled FORCED_COVERAGE paper trades when PRIMARY has not traded, targeting at least one paper trade per executable contract. Coverage uses the current executable quote at entry.
- PRIMARY, FORCED_COVERAGE and SHADOW_REJECTED remain isolated for analysis.
- Corrected RDFZ export filename/version to V2.28.30.
- Auto Paper remains enabled by default at server startup.
- Production Decision, Settlement, GT and other prediction architectures are unchanged.

## Validation
- Final Target complete-minute retention: 60/60.
- Final Target sample count monotonic in synthetic complete-minute test.
- Last-tick-per-source-second selection verified.
- Shadow trade deduplication/isolation verified.
- Primary gate entry verified.
- Forced coverage fallback verified.
- Multi-contract executable-book coverage test passed.
