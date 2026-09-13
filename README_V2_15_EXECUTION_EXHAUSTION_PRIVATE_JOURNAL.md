# V2.15 — Execution Workflow + Private Trade Journal

Adds a Trade Execution panel while preserving V2.14's centered chart, indicators, FLIP/RE-FLIP, MP, TR and order-flow display.

New UI: Market Decision vs Trade Decision; Kalshi YES/NO best bid/ask; gross entry multiplier; desired max entry price; ENTRY WINDOW OPEN vs WAIT / DON'T CHASE; optional private position entry; live executable-bid P&L; independent Exhaustion 0–100; Reversal Confirmation; position-aware HOLD / PROTECT PROFIT / EXIT.

Multi-user safety: positions and journals are stored in browser `localStorage`, not Python globals, so users do not overwrite each other. The server only serves shared market analysis. A user can export the private journal as CSV. Journal rows capture ticker/time, BRTI/target/time remaining, Chart/Decision/MP, exhaustion/reversal, RSI/J/MACD, Kalshi bid/ask, entry/exit information and trade-decision transitions.

Persistence note: browser localStorage survives normal refresh/restart but is device/browser specific and can be erased by clearing site data. Export CSV is the durable backup. Server-side durable multi-device trade storage should only be added later with authentication plus a persistent database; Render's local filesystem should not be treated as durable user storage.

No automatic orders are submitted to Kalshi. Kalshi prices are execution/research inputs only and do not feed Chart Signal or settlement Decision.
