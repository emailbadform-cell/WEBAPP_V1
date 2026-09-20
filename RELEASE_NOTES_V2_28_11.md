# V2.28.11 temporary GT gap consumption
Builds on the confirmed-working V2.28.10 realized-candle replacement.

- Initial layout: frozen Previous | frozen Current | GAP | GAP | GT1 ... GT15.
- After the first GT minute becomes actual, all GT slots shift left one position, consuming one gap.
- After the second GT minute becomes actual, all GT slots shift left a second position, consuming the final gap.
- Thereafter there is no visual gap; realized actual candles and remaining projected GT candles form a continuous sequence.
- The original previous/current BRTI context candles remain frozen.
- Realized GT slots retain actual BRTI OHLC and green/red coloring.
- Future GT slots remain live recursive projections.
- No forecasting/trading/API/feed/contract logic changed.
