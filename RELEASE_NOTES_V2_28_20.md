# V2.28.20 / V10.39.10 — Instrumentation-only update
- No Decision, Settlement2, GT1–GT15, Auto Paper V1 entry, or Auto Paper V1 exit authority changes.
- Adds 0.5s prospective synchronized architect snapshots.
- Adds 5s Kalshi WS health summaries.
- Enriches Auto Paper events with app/research version, state sequence, quote timestamp/age, sid/seq and settlement provenance.
- Explicitly marks rollover settlement as PROXY_NOT_OFFICIAL.
- Adds GET /api/instrumentation/status.
- Persistent deployment should set TRADE_EVENT_LOG_PATH, AUTO_PAPER_STATE_PATH, PROSPECTIVE_LOG_PATH and WS_HEALTH_LOG_PATH to a mounted disk.
