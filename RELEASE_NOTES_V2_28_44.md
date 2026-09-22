# V2.28.44 — GT-C Actual Replacement + GT-B Anticipation
- Replaces active GT path with GT-C actual-replacement deltas.
- Adds GT-B actual-anchor forward-skip anticipation challenger inside GT telemetry.
- Retires dependency-weighted predicted-anchor GT-A from active computation.
- Keeps Decision, Settlement, and trading authority unchanged.
- Keeps existing Web GT visual sequence unchanged: frozen two real context candles, temporary one-slot gap, projected slots morph to actual.
- Web renderer re-anchors the next GT-C forecast to the actual BRTI close whenever a GT slot realizes.
