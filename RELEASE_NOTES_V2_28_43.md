# BTC15M Web V2.28.43 — Data Quality / Validation Hardening

- Production Decision, Settlement, and frozen Auto Paper policy logic remain unchanged.
- Adds fail-closed BRTI freshness gate (>2.5s blocks new Auto Paper entry).
- Adds fail-closed execution-book freshness gate (>2.0s blocks new Auto Paper entry).
- Adds `data_quality` state with model/execution validity flags.
- Keeps Kalshi CF Benchmarks Final Target as sole displayed/live authority; local reconstruction remains diagnostic only.
- Preserves direct RDFZ raw-file download introduced in V2.28.42.
- GT remains a pure BRTI path. GT1-GT15 are preserved; Final Target is not substituted for GT15.
- Version/log metadata advanced to V2.28.43 / V10.39.25 for synchronized collection.
