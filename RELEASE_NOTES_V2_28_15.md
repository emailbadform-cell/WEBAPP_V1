# Web V2.28.15 — Faster KXBTC15M rollover

Built from the working V2.28.14 baseline.

Changes:
- Begins deterministic next-contract prefetch 300 seconds before expiration (was 90s).
- Retries the exact expected KXBTC15M ticker every 0.5s while not ready (was 1.0s).
- Retains 2s broad-list fallback during prefetch.
- Retains 0.35s direct deterministic retry and 0.5s broad fallback after expiration.
- Records first direct response, first target availability, prefetch-ready time, rollover mode,
  and rollover latency so live sessions can identify whether delay is Kalshi publication,
  backend discovery, or promotion.
- Existing prefetched contract remains authoritative at expiration and switches immediately.
- No changes to Decision, Settlement 2.0, GT authority, BRTI SSE, or research prediction logic.
