# BTC15M Web V2.28.0

- Preserves Decision, TR, Settlement separation, Entry Quality, and Profit Protection trading logic from V2.26.1.
- Moves the first GT visual projection from one candle slot away to two candle slots away. This is display-only; GT calculations are unchanged.
- GT line uses the same two-slot visual start.
- Keeps V2.26.1 trade lifecycle logging for future Entry Quality / Profit Protection validation.
- No unvalidated GT14/GT15, OF/L2, or Settlement research result is promoted into trading authority.
