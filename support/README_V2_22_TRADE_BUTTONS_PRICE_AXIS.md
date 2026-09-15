# BTC15M Web V2.22 / Research Context V10.34

## Purpose
V2.22 is a web/UI execution-control and chart-display update built from V2.21. It preserves the existing production/research signal architecture and does not give manual trade controls authority over Forward, Decision, GT, TR, MP, OF, L2, FLIP/RE-FLIP, or settlement logic.

## Changes
- BRTI feed age is moved to the far-right edge of the BRTI metric box.
- The text `LIVE`/`STALE` is removed from beside the BRTI price. Feed age remains color-coded: green while fresh, red when stale.
- Replaces the single TAKE TRADE control with two explicit manual direction buttons when no position is active:
  - **TAKE TRADE UP** = manual ABOVE / Kalshi Yes-side tracking.
  - **TAKE TRADE DOWN** = manual BELOW / Kalshi No-side tracking.
- Once either trade is armed, both entry buttons are replaced by one **EXIT TRADE** button.
- After EXIT TRADE, the two entry buttons reappear immediately for a new manual trade.
- Manual trade entry uses the selected side's current ask and tracks that side's bid for profit-protection calculations.
- Adds a right-side chart price axis with readable BRTI price levels.
- Adds a highlighted live BRTI price marker and horizontal guide line on the chart.
- Existing target line, EMA9/EMA21, GT projected candles, GT line/off selector, and 1m/5m/10m/15m display selector remain intact.

## Preserved architecture
- Trade buttons are browser-local tracking controls only. They do not place Kalshi orders.
- UP/DOWN manual selection does not alter the predictive Decision or any model output.
- Kalshi YES/NO prices remain execution context only and do not influence Forward.
- GT remains 1m predictive visualization; higher chart timeframes are display aggregation only.
- L2/OF remain non-authoritative research/display context.

## Chart price display
The chart reserves a narrow right-side axis. Tick spacing is selected dynamically from the currently visible price range. The current BRTI marker uses the live BRTI value from the state payload when available, rather than assuming the most recent candle close is identical to the live price.

## Manual-direction compatibility
Because V2.22 allows a user to deliberately track either side, profit protection no longer treats an already-opposing predictive Decision as if a new Decision flip just happened. The Decision present at manual entry is stored, and the immediate flip condition fires only when Decision changes after entry. An opposing current Decision still counts as a deterioration/risk factor.
