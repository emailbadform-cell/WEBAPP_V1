# V2.28.21 / V10.39.11 — RDFZ data-folder update

Instrumentation/storage only. Prediction and Auto Paper authority are unchanged.

Set one Render environment variable:
RDFZ_DIR=/var/data/RDFZ

All research/runtime files needed for follow-up analysis now default into RDFZ:
- BTC15M_AUTO_PAPER_EVENTS.ndjson
- BTC15M_AUTO_PAPER_STATE.json
- BTC15M_V10_39_11_PROSPECTIVE_ARCHITECT_SNAPSHOTS.ndjson
- BTC15M_WS_HEALTH_SUMMARY.ndjson
- BTC15M_KALSHI_WS_EVENTS.ndjson
- BTC15M_CLIENT_LATENCY.ndjson
- BTC15M_V10_39_11_RESEARCH_LOG.csv

GET /api/rdfz/status lists the folder contents.
GET /api/rdfz/download creates/downloads a single RDFZ.zip containing the folder plus RDFZ_MANIFEST.json.

No credentials are copied into RDFZ.
