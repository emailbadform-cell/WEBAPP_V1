# BTC15M Architecture Audit — 2026-09-21 prospective block

Dataset: Web V2.28.38 compact, 800 snapshots across 26 contracts; Research raw BRTI supplied 60/60 source-second settlement reconstruction for 25 completed contracts.

Key prospective results (snapshot-weighted; repeated snapshots within contracts are correlated):
- Decision: 66.8% overall; 84.6% <=180s; 87.1% <=120s; 88.2% <=60s.
- Settlement: 67.7% overall; 84.2% <=180s; 87.1% <=120s; 88.8% <=60s.
- Chart: 60.8% overall. MP: 62.0%.
- GT directional endpoint vs G0: GT1 47.5%, GT3 57.3%, GT5 56.7%, GT10 56.5%, GT11 58.5%, GT15 62.5%.
- Validated OF: 50.7% overall; OF Micro directional subset 58.7%. Broad OF remains context-only.
- Forward: 56.0% overall and 47.8% <=60s; retain as path/context, not final-winner authority.
- Transition V2 runtime plumbing is fixed: 374 armed/triggered snapshots across 25 contracts. Its direction is a structural-transition forecast, not a final-winner forecast; no winner override is promoted.
- Web rollover telemetry: median recorded rollover latency ~0.012s; maximum ~395ms in this block.
- Auto Paper: 26 entries/exits. Using 60/60 reconstructed BRTI for expiry accounting, 20 expiry holds had 18 reconstructed wins. Corrected dataset P&L is +$560.58 vs logger +$669.31. Primary: 16 trades, corrected +$468.71; Forced Coverage: 10 trades, corrected +$91.87. These are reconstructed, not official Kalshi outcomes.

Confirmed defects/fixes:
1. V2.28.38 Final Target still capped at 0-2 samples. Root cause: settlement_window_state replaced the engine tick buffer whenever preserved_seconds contained even one item. V2.28.40/V10.39.24 merge both sources and deduplicate by source second. Synthetic 60/60 test passes exactly.
2. Expiry paper P&L used last-observed BRTI. V2.28.40 uses complete 60-source-second reconstructed settlement when available; incomplete windows are explicitly labeled fallback proxy.
3. Research log/export version labels were stale (V10_39_14/V10.39.15). V10.39.24 corrects them.

No production Decision/Settlement/GT/TR/Flip/Primary gate mathematics were retuned from this block. The evidence supports specialization and further shadow challengers rather than in-sample promotion.
