# V2.28.12 GT minute alignment + one-gap layout

Builds on V2.28.11.

- Corrected GT/BRTI alignment: GT1 corresponds to the 1m interval starting at the contract/thread origin, not origin+1m.
- GT1 becomes actual after origin+1m, GT14 after origin+14m, and GT15 after origin+15m.
- Therefore with only seconds left in the contract, GT1-GT14 should already be actual and only GT15 should remain projected.
- Initial visual spacing reduced from two empty candle slots to one.
- Initial: Previous | Current | GAP | GT1 ... GT15.
- Once GT1 becomes actual, the one gap is consumed and the sequence becomes continuous.
- Original Previous/Current candles remain frozen.
- Actual GT candles retain exact BRTI OHLC and green/red rendering.
- Future GT candles remain live recursive projections.
- No Decision, Settlement, OF/L2, forecast-generation, startup, BRTI-feed or contract-discovery logic changed.
