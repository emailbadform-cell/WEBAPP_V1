# V2.28.7 rolling GT chart
- GT chart first two candles are previous real BRTI 1m and current developing BRTI 1m.
- Keeps two fixed empty visual slots after the current BRTI candle.
- As each projected minute becomes real, its GT projection rolls off the right-side sequence.
- The newly available real BRTI candle enters the two-candle real window with actual OHLC and green/red direction.
- Remaining GT candles shift left and remain recursive projections.
- No Decision, Settlement, GT forecast-generation, OF/L2, contract-discovery, startup, or BRTI-feed logic changed.
