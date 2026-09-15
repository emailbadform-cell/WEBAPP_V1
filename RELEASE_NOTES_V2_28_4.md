# V2.28.4 non-blocking startup/API recovery
- Adds /api/ping that never waits on engine/feed/cache locks.
- /api/state cache reads are lock-free and immediately return either the last completed snapshot or an explicit warming payload.
- State cache publishes snapshots by atomic reference assignment.
- Browser state requests have an 8-second abort timeout, so refreshBusy cannot remain stuck forever.
- Browser independently probes /api/ping every 5 seconds with a 3-second timeout.
- Startup panel now distinguishes web API liveness, cache warming, engine creation, history rows, and completed state.
- No Decision, Settlement, GT forecasting, OF/L2 scoring, or trading logic changed.
