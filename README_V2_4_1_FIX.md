# V2.4.1 Frontend Connection Fix

This fixes a V2.4 frontend JavaScript regression introduced while removing the standalone Coinbase Order Flow panel.

The deleted panel's rendering code was on the same JavaScript line as the end of the refresh() function.
Removing that line accidentally removed:
- chart update
- redraw call
- catch/error handler
- closing brace for refresh()

That caused the browser JavaScript to fail before it could poll `/api/state`, leaving the dashboard stuck on `Connecting...`.

V2.4.1 restores the refresh loop while keeping:
- no standalone Coinbase OF panel
- one Multi-Exchange Order Flow panel
- Coinbase/Kraken/Bitstamp/Gemini/Combined/Consensus
- no exchange spot prices
- no web logging
- unchanged prediction logic
