# V2.28.8 GT rolling fix
V2.28.7 did not roll because the recursive GT `t0` is regenerated on every live BRTI update, causing the elapsed/realized counter to reset to zero. V2.28.8 freezes the GT chart's contract-local minute origin while leaving the GT forecast values live and recursive.

- First two candles: previous real BRTI 1m + current/developing real BRTI 1m.
- Two visual empty slots remain fixed.
- One GT projection rolls off after each completed minute.
- Remaining GTs move left without stretching back across the chart.
- Real candles use actual BRTI OHLC and green/red candle coloring.
- Rolling origin resets on contract ticker rollover.
- Forecast generation and trading logic are unchanged.
