# BTC15M Web App V2.5 — V10.19 TR + OF Decision

This is the Render-ready, no-research-logging web build paired with the V10.19 research predictor.

Visible additions:
- V10.19 calibrated Target Reachability probability
- raw TR probability for comparison
- OF target context: TOWARD TARGET / NEUTRAL / AWAY FROM TARGET
- OF Early Detection
- OF Micro (~10 second research context)
- MP / OF support-conflict context
- Decision Fusion / risk
- Combined multi-exchange OF threshold +/-0.15
- Current-side anchored V10.18/V10.19 Decision logic

Important architecture:
- Chart Signal remains chart-only.
- TR probability is calibrated from historical live research and OF does not alter it yet.
- OF provides target-direction, micro-horizon, and conflict/risk context.
- No CSV research logger is invoked by this web service.
- BRTI remains the Kalshi settlement price reference.

Render:
- Health check: /api/health
- KALSHI_API_KEY_ID environment variable
- Render Secret File: kalshi_private_key.pem (or KALSHI_PRIVATE_KEY_PEM env var)
