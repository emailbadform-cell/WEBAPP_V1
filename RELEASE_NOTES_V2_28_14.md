# V2.28.14 — Prospective Latency Instrumentation

No architect authority changes. Preserves V2.28.13 behavior and V2.28.12 Ghost Thread chart semantics.

Adds a BRTI-only SSE push path so the displayed BRTI can update on each newly received engine quote without waiting for the 1-second full-state poll. Adds browser receipt/render telemetry for source→server→browser latency measurement. Full state remains on the existing nonblocking cache path.
