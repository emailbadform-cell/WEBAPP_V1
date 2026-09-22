# BTC15M Web V2.24.7 — Fast Initialization

Research architecture remains V10.35.

## Web initialization fix
- Starts the authenticated BRTI 5 Hz WebSocket immediately instead of waiting for the 6-hour historical BRTI download.
- Loads the 6-hour BRTI history in a parallel background thread.
- Retries initial Kalshi KXBTC15M contract discovery continuously; a transient startup failure no longer terminates the main data worker.
- Retains/retries the newest live BRTI tick while model context is warming.
- REST BRTI remains a recovery/bootstrap path and no longer turns a startup problem into a terminal state.
- Coinbase fallback remains disabled by default and is not used as the primary initialization fix.
- No Forward, Decision, TR, GT, FLIP/RE-FLIP, MP, L2/OF authority, or Profit Protection model thresholds were changed.

## Versioning
- Web: V2.24.7
- Research: V10.35 (unchanged)
