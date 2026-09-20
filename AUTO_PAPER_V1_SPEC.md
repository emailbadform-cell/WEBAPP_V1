# Auto Paper V1 — Frozen Prospective Collection

**Status:** paper-only, research-only. **Predictive authority:** unchanged.

Entry: Decision side must agree with Settlement, remain unchanged for >=2 seconds, 20–180 seconds must remain, and the selected side ask must be <=75c. One active paper position at a time. $100 notional uses the existing paper trader.

Primary autonomous exits: opposing Decision confirmed for >=5 seconds; >=8c/contract favorable move followed by >=5c giveback; >=8c/contract profit with <=45 seconds remaining; or the existing EXIT profit-risk state while the position is profitable. Expiry/rollover settlement behavior is preserved.

Every eligible/noneligible opportunity is also sampled into the trade-event stream with gate state and a frozen list of shadow policies. Shadow policies never control the primary paper position.

Kalshi prices are execution/value/P&L inputs only. They are not inputs to Decision, Settlement, Ghost Thread, Chart, MP, or other predictive authority.

This V1 is deliberately a data-collection policy, not a claim of proven profitability. Do not optimize it contract-by-contract; collect a prospective block before refinement.
