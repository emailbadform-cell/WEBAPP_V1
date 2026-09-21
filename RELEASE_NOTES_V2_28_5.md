# V2.28.5 resilient BRTI startup
- Fixes the engine worker permanently exiting when the initial six-hour BRTI backfill fails.
- Seeds immediately from the lightweight recent BRTI /values path.
- Retries recent BRTI continuously if the first request fails.
- Historical six-hour BRTI backfill is non-fatal and retried in the background at most once per minute.
- Live state can publish from recent BRTI while history/model warm.
- /api/ping exposes the current engine error so BRTI failures are visible.
- Preserves V2.28.4 non-blocking /api/state and /api/ping behavior.
- No Decision, Settlement, GT, OF/L2 scoring, or trading-authority logic changed.
