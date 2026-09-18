# V2.28.3 Component startup diagnostics
- Expands startup diagnostics to show Contract, BRTI, Chart, GT, OF and L2 independently.
- Shows raw API ticker, BRTI value, candle count, sparkline count and GT endpoint count.
- Ready now means current Contract + live BRTI are available; slower architects may continue warming.
- Preserves the 45s waiting and 180s stalled diagnostics.
- No trading, Decision, Settlement, GT forecasting, OF/L2, or model logic changed.
