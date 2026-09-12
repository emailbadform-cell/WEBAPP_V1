# BTC15M Web V2.14 / Research Core V10.30

## Visible changes

- Removes the Target Reachability **Role / Reversal Risk** row from the dashboard. Its underlying value remains available in backend/research state.
- Adds **RSI 14**, **KDJ J (9/3/3)** and **MACD histogram (12/26/9)** under Structure.
- Adds separate **RE-FLIP** status and the high-confidence RE-FLIP rule.
- Initial FLIP display now shows **TR >=60% · no fixed dollar cap**.
- Latest candle/line point stays around **69% of chart width**, leaving stable future space to the right as new candles build.
- `Live centered` redraw control restores the centered live layout.

Indicators are display/research-only and do not alter Chart Signal, Decision, TR, FLIP, MP, or OF.
