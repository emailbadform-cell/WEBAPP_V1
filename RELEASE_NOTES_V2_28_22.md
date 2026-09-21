# V2.28.22 / V10.39.13
RDFZ + rollover reliability update based on the first clean Web RDFZ capture.

Observed in the supplied capture:
- 83 prospective snapshots across two tickers.
- Old contract remained displayed at seconds_left=0 through multiple snapshots.
- First new-contract prospective snapshot arrived more than one minute after the first zero-time snapshot.
- Kalshi WS itself already had current + next books and reported no sequence gaps.
- Auto Paper was in shadow mode: 76 SHADOW_OPPORTUNITY events, no ENTRY/EXIT.
- Four entry-window snapshots passed the frozen gate; no policy authority was changed.

Changes:
- Adaptive deterministic next-market REST prefetch: 10s cadence >60s remaining, 3s at 15-60s, 1s at 0-15s, 0.35s after expiry. This reduces pre-expiry request pressure while preserving fast boundary retry.
- Prospective RDFZ snapshots now include rollover telemetry needed to isolate discovery vs activation latency.
- Prediction architecture authority and frozen Auto Paper policy unchanged.
