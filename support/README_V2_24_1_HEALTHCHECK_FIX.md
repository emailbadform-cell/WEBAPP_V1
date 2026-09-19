# BTC15M Web V2.24.1 / V10.34 — Render Health Check Fix

This patch changes only the service health-check behavior.

- `/api/health` is now a liveness endpoint and always returns HTTP 200 while FastAPI is alive.
- Market-data readiness is reported in the JSON body as `LIVE`, `WARMING`, or `STALE`.
- Cache age and cache errors remain visible for diagnostics.
- No Forward, Decision, GT, MP, TR, OF/L2, FLIP, chart, timer, trade accounting, or Profit Protection logic was changed.
- Profit Protection remains frozen pending additional research data.
