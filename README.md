# BTC15M Web V2.24.6

Deployment package for the BTC15M/Kalshi web application.

Version identity: **Web V2.24.6**
Research version paired with this build: **V10.35**

V2.24.6 UI change:
- Adds a `GT NEXT 1M` direction tile in the Core Signals / prediction area.
- `UP` displays green, `DOWN` displays red, and unavailable state displays `—`.
- The tile reflects the same GT direction that drives the projected 1-minute candle; it is not a separate model.

Inherited V2.24.5 reliability fixes remain in this web build, including predictive Decision plumbing, MP signed/adverse progress handling, and deterministic rollover/prefetch work.

No GT model logic, TR rules, FLIP/RE-FLIP rules, Forward thresholds, Profit Protection thresholds, or L2/OF authority were changed for V2.24.6.
