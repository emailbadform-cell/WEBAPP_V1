# BTC15M Web V2.19 / Research V10.33

## Display update
- Full-width 90-minute candlestick chart.
- Kalshi target line remains on the chart.
- EMA9/EMA21 remain chart overlays only and are removed from Advanced Diagnostics.
- Core Signals moved below the chart into a horizontal compact grid.
- Structure remains visible.
- Only combined Order-Flow Consensus is displayed; per-exchange OF stays computed/logged.
- Move Projection, Direction, Strength, Exhaustion, Progress and Remaining remain visible.
- Advanced Diagnostics are open by default and can be hidden.

## Manual trade tracking
- TAKE TRADE records the current Decision-side Kalshi ask as the browser-local reference entry.
- The button changes to EXIT TRADE.
- Profit Protection and Exit Signal are evaluated only while a manually tracked trade is active.
- Exit/protection signals never automatically clear the tracked trade. The user presses EXIT TRADE to close/reset it.
- A contract rollover automatically clears a stale tracked trade.
- No order is sent to Kalshi; this is tracking only.

## Isolation
- Chart, Decision, TR, FLIP/RE-FLIP, MP, OF calculations and rollover backend are unchanged from V2.18/V10.32.
- This release changes web presentation and browser-local trade tracking only.
