# V2.28.9 frozen GT context candles
- Captures the original previous and current BRTI 1m candles when the GT thread/contract starts.
- Freezes copies of their timestamp and actual OHLC for the life of that contract.
- The two left-side context candles no longer roll forward.
- The two visual gap slots remain fixed.
- GT projections continue rolling left one per completed minute and remain live/recursive.
- Frozen context resets on contract ticker rollover.
- Trading/forecast generation, Decision, Settlement, OF/L2, startup, BRTI feed and contract discovery are unchanged.
