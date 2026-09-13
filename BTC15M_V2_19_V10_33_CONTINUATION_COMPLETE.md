# BTC15M V2.19 / V10.33 Continuation

## Web V2.19
- Full-width candlestick chart, target line, EMA9/21 chart overlays.
- Horizontal Core Signals below chart.
- Structure remains visible.
- Only combined OF Consensus shown; individual venue OF remains computed/logged.
- Move Projection, Direction, Strength, Exhaustion, Progress and Remaining visible.
- Advanced Diagnostics visible by default and collapsible; EMA values are not repeated there.
- Manual TAKE TRADE / EXIT TRADE tracking activates browser-local profit protection.
- Profit/exit signals advise; they do not auto-close the manual tracked trade.

## Research V10.33
- Visual web redesign is not copied to research.
- `RESEARCH_DATA/` is the standard single-folder handoff.
- Future live research log writes to `RESEARCH_DATA/raw/BTC15M_V10_33_RESEARCH_LOG.csv`.
- Raw historical logs, derived research outputs, model artifacts, validation reports and specs are packaged under that folder with SHA-256 manifest.

## Preserved
Chart/Decision/TR/MP/OF/FLIP/RE-FLIP calculations and backend rollover logic remain inherited from V2.18/V10.32 unless separately researched/promoted. Kalshi YES/NO prices remain execution context only.
