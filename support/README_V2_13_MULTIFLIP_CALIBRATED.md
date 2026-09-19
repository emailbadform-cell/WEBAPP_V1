# Web V2.13 / Core V10.29

Changes from V2.12:

- FLIP automatically resets after each actual cross-through so the same 15-minute contract can record multiple flips.
- Adds **Session flips** and **FLIP cycle** to the Target Reachability panel.
- FLIP confirmation now shows `FLIP #N — CROSS THROUGH CONFIRMED` briefly, then returns to the fresh RE-FLIP cycle.
- Calibrated arm is widened to **$20 + TR >=65%**.
- The fixed calibration produced 15/15 development and 8/8 later forward qualifying contracts crossing, 23/23 observed overall. This is empirical validation, not a future guarantee.
- Existing V2.12 chart continuity, deterministic rollover prefetch, stabilized MP lifecycle, TR, order flow, and Decision logic are preserved.
