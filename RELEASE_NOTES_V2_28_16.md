# BTC15M Web V2.28.16
Built from the proven V2.28.15 rollover baseline.

Adds the same V10.39.6 research-only target/pressure instrumentation to the web runtime logger:
EMA3-vs-target, CH3 research geometry, target-cross counts, OF response, multi-venue L2 consensus/response.

Preserved:
- V2.28.15 300s next-contract prefetch and rollover path;
- BRTI SSE and client telemetry;
- frozen Previous/Current BRTI Ghost Thread context;
- one-gap GT realization mapping;
- recursive GT behavior;
- Decision and Settlement 2.0 authority.

No new winner/Decision/Settlement authority and no new trading UI signal is promoted in this release.
