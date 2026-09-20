# BTC15M Web V2.25.0

Deployable website package. Research architecture is V10.36.

V2.24.7 fixes slow/stalled initialization by starting live BRTI immediately, running historical BRTI backfill in parallel, and continuously retrying Kalshi active-contract discovery instead of terminating the worker after a transient startup failure.

The real Kalshi private key is intentionally not packaged. Configure credentials in the deployment environment/local secret path. Do not commit private keys.

## V2.28.34 RDFZ export behavior
RDFZ download is cumulative and non-destructive. Active logs are never moved by export. A temporary verified ZIP is streamed to the client and deleted after transfer, avoiding duplicate `_exports` storage. All currently retained active data remains available for the next export.
