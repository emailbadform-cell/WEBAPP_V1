# BTC15M Web V2.26.1 / Research V10.37

## Runtime fixes
- Fixes `/api/health` 500 caused by boolean evaluation of a pandas DataFrame.
- Applies the same safe history-row handling to `/api/state` warmup responses.
- Restores `POST /api/trade-event` and `GET /api/trade-events/status`.
- Restores browser paper-trade lifecycle logging for ENTRY, approximately 1-second UPDATE, EXIT, and POST_EXIT at 5/10/30/60/120 seconds when the same contract remains available.
- Trade events record peak/trough bid, MFE/MAE and current model context for later Entry Quality / Profit Protection research.

## Architecture
- Research remains V10.37.
- Decision logic is unchanged.
- Settlement remains separate and research-only.

## Storage
The default trade-event log is `/tmp/btc15m_trade_events.ndjson`. Set `TRADE_EVENT_LOG_PATH` to a mounted persistent volume path if events must survive application redeploys/restarts.
