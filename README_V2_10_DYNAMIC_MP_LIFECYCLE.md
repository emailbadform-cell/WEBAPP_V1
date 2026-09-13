# BTC15M Web V2.10 — Dynamic MP Projection Lifecycle

Paired with research/core V10.26.

Move Projection Near/Base/Extended and Progress now refer to one fixed projection leg. Once Base is achieved, the dashboard immediately starts a fresh projection leg from current BRTI instead of remaining at 100-200% progress. The MP panel shows lifecycle status and completed-leg count.

All V2.9 functionality remains unchanged otherwise. Deploy the full package because app.py, live_btc15m_predictor.py, and static/index.html are version-coupled.
