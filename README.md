# BTC15M Web V2.24.7

Deployable website package. Research architecture remains V10.35.

V2.24.7 fixes slow/stalled initialization by starting live BRTI immediately, running historical BRTI backfill in parallel, and continuously retrying Kalshi active-contract discovery instead of terminating the worker after a transient startup failure.

The real Kalshi private key is intentionally not packaged. Configure credentials in the deployment environment/local secret path. Do not commit private keys.
