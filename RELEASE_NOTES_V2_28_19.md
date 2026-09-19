# BTC15M Web V2.28.19

Infrastructure correction release. Prediction authority is unchanged from V2.28.18.

- Auto Paper V1 moved from browser JavaScript to the backend server. It continues when no browser is connected.
- Auto Paper V1 policy remains frozen: Decision+Settlement agreement, 2s Decision persistence, 20–180s remaining, ask <= 75c; existing V1 exit rules preserved.
- Manual paper positions remain browser-owned and are fully separate from the server AUTO_V1 position.
- Server records AUTO_MODE, SHADOW_OPPORTUNITY, ENTRY, UPDATE and EXIT lifecycle events.
- Auto state can be persisted with AUTO_PAPER_STATE_PATH; trade events with TRADE_EVENT_LOG_PATH.
- Kalshi WebSocket sequence handling corrected to subscription scope using sid+seq, allowing current/next ticker messages to interleave without false gaps/reconnects.
- Raw Kalshi WS records now retain sid.
- Prediction firewall preserved: Kalshi price/book information remains execution-domain only.
