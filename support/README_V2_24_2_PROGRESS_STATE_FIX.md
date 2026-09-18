# BTC15M Web V2.24.2 / V10.34 — Progress State Fix

This patch is intentionally narrow.

- Move Projection **Progress** is recalculated in the browser from the active projection leg anchor/base and the current BRTI on every valid dashboard refresh.
- A genuine mathematical 0% is still displayed when price is at/behind the active leg anchor.
- Incomplete or malformed transient updates on the **same ticker and projection leg** no longer overwrite the last valid Progress/Remaining display.
- A new ticker or new projection leg clears the held display so stale values cannot leak across lifecycle boundaries.
- The V2.24.1 `/api/health` liveness fix is retained (HTTP 200 while FastAPI is alive).
- Profit Protection remains unchanged pending additional research data.
- No Forward, Decision, GT, MP model, TR, OF/L2, FLIP, or research-model logic changed.
