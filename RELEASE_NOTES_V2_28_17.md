# V2.28.17 — Auto Paper V1

Adds frozen prospective autonomous **paper-only** entry/exit and shadow-policy collection. No predictive architect authority changes.

Primary collection entry gate: Decision + Settlement agreement, Decision stable 2s, 20–180s remaining, side ask <=75c. Primary paper exit: 5s confirmed Decision opposition, >=8c profit with >=5c giveback, >=8c profit at <=45s, or existing EXIT profit-risk state while profitable. All events use existing /api/trade-event lifecycle logging. Shadow opportunities are logged independently for later prospective comparison.

AUTO PAPER is OFF by default and persisted locally when explicitly enabled. Manual paper trading remains available. No live Kalshi order endpoint is added.
