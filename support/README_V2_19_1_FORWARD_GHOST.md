# BTC15M Web V2.19.1 — Forward Signal + Ghost Thread

V2.19.1 is a web/UI integration update over the V2.19 / V10.32 core with V10.33 research context.

Changes:
- Dedicated Forward Signal tile using BRTI-only frozen V10.33 champion feature families: 5s/10s FULL_PATH logistic, 30s/60s RETURNS logistic.
- Deployment models are fitted on the currently available touched historical research set for live inference. This is not new untouched validation; future unseen sessions remain required for prospective confirmation.
- Forward inputs exclude Kalshi YES/NO prices, target, current side, Decision, TR, MP, and OF.
- Ghost Thread starts at latest BRTI and projects the active Forward direction into future chart space with a gray/white dashed guide and uncertainty corridor. It does not claim exact-dollar forecast precision.
- EMA 9 changed to light blue; EMA 21 changed to purple/pink; chart legend identifies EMA 9, EMA 21, Ghost Thread, and Target.
- BRTI feed age/status moved beside the BRTI price in the top summary and removed from Advanced Diagnostics.
- Advanced Diagnostics reorganized into Forward Signal, Target Reach & Settlement, Move Projection, Order Flow, Chart & Momentum, Decision & Risk, and Contract & System groups.
- Existing Chart/Decision/TR/MP/OF/FLIP/RE-FLIP/profit-protection/rollover logic remains inherited unless explicitly described above.
