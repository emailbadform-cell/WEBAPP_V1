# BTC15M Web V2.19.2

Web-only patch over V2.19.1. Research remains V10.33 and core signal logic remains inherited from V10.32.

Changes:
- Ghost Thread now remains visible when Forward Signal is SIDEWAYS. The centerline stays nearly horizontal and uses a wider uncertainty corridor.
- Directional Ghost Thread behavior remains tied to Forward Signal; no Forward thresholds were loosened.
- BRTI feed-age/live indicator has more separation from the BRTI price.
- STRONG move-projection strength is displayed in green.
- `/api/state` now serves the latest completed background snapshot so slow state construction does not block browser requests and cause transient Render 502 errors.
- The browser preserves the last good dashboard state during transient API misses and only surfaces a raw HTTP error after repeated failures.

No Kalshi YES/NO price is used by Forward Signal or Ghost Thread. No research thresholds or core trading logic were changed.
